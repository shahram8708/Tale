"""
TALE language engine with Python-mapped execution.
The goal is to let beginners learn Python concepts using readable English-style syntax.
"""

from __future__ import annotations

import ast
import io
import json
import csv
import math
import os
import random
import re
import shlex
import sys
import textwrap
from contextlib import redirect_stdout
from datetime import datetime
from typing import Dict, List, Optional, Tuple


class TaleSyntaxError(Exception):
    """Raised when TALE code cannot be translated."""


class InputExhausted(Exception):
    """Raised when the program asks for more input than was provided."""


class TaleInterpreter:
    def __init__(self, code: str, inputs: Optional[List[str]] = None) -> None:
        self.code = code
        self.inputs = inputs or []
        self._input_index = 0

    # Input is pulled from the supplied list for deterministic execution.
    def input_provider(self) -> str:
        if self._input_index < len(self.inputs):
            raw = self.inputs[self._input_index]
            self._input_index += 1
            value = str(raw)

            # Auto-coerce numeric-looking inputs so math works naturally.
            if re.fullmatch(r"[+-]?\d+", value):
                return int(value)
            if re.fullmatch(r"[+-]?(\d+\.\d*|\d*\.\d+)", value):
                try:
                    return float(value)
                except ValueError:
                    return value

            return value
        raise InputExhausted(
            "No more inputs were supplied. Add values in the Inputs box (one per line)."
        )

    def to_python(self) -> str:
        py_lines: List[str] = []
        indent = 0
        in_note = False
        note_delim = '"""'

        for line_no, raw_line in enumerate(self.code.splitlines(), start=1):
            original = raw_line.rstrip("\n")
            stripped = original.strip()

            if in_note:
                if stripped.endswith(note_delim):
                    in_note = False
                continue

            if not stripped or stripped.startswith("#"):
                continue

            lowered = stripped.lower()

            if lowered.startswith("note " + note_delim):
                if not stripped.endswith(note_delim):
                    in_note = True
                continue

            if lowered == "end":
                indent = max(indent - 1, 0)
                continue

            if lowered.startswith("elif "):
                indent = max(indent - 1, 0)
                condition = stripped[5:].strip()
                condition = self._transform_expr(condition)
                self._validate_expr(condition, original)
                py_lines.append(self._pad(indent) + f"elif {condition}:")
                indent += 1
                continue

            if lowered == "else":
                indent = max(indent - 1, 0)
                py_lines.append(self._pad(indent) + "else:")
                indent += 1
                continue

            if lowered.startswith("catch "):
                indent = max(indent - 1, 0)
                err_name = stripped[6:].strip() or "error"
                self._validate_name(err_name, original)
                py_lines.append(self._pad(indent) + f"except Exception as {err_name}:")
                indent += 1
                continue

            if lowered == "finally":
                indent = max(indent - 1, 0)
                py_lines.append(self._pad(indent) + "finally:")
                indent += 1
                continue

            try:
                python_line, opens_block = self._translate_line(original)
                py_lines.append(self._pad(indent) + python_line)
                if opens_block:
                    indent += 1
            except TaleSyntaxError as exc:
                raise TaleSyntaxError(f"Line {line_no}: {exc}") from exc
            except Exception as exc:  # noqa: BLE001
                raise TaleSyntaxError(f"Line {line_no}: {exc}") from exc

        return "\n".join(py_lines)

    def _pad(self, indent: int) -> str:
        return "    " * max(indent, 0)

    def _translate_line(self, line: str) -> Tuple[str, bool]:
        stripped = line.strip()
        lowered = stripped.lower()

        # Control blocks
        if lowered.startswith("if "):
            condition = self._transform_expr(stripped[3:])
            self._validate_expr(condition, line)
            return f"if {condition}:", True

        if lowered.startswith("while "):
            condition = self._transform_expr(stripped[6:])
            self._validate_expr(condition, line)
            return f"while {condition}:", True

        if lowered == "try":
            return "try:", True

        if lowered.startswith("function "):
            header = stripped[9:].strip()
            name, params = self._parse_fn_header(header, line)
            return f"def {name}({params}):", True

        if lowered.startswith("generator "):
            header = stripped[10:].strip()
            name, params = self._parse_fn_header(header, line)
            return f"def {name}({params}):", True

        if lowered.startswith("class "):
            class_def = stripped[6:].strip()
            return f"class {class_def}:", True

        if lowered.startswith("with file ") and " as " in lowered:
            before_as, alias = stripped[9:].split(" as ", 1)
            file_expr = self._transform_expr(before_as.strip())
            alias_name = alias.strip()
            self._validate_name(alias_name, line)
            py = f"with _open_file({file_expr}, 'r') as {alias_name}:"
            return py, True

        if lowered.startswith("with ") and " as " in lowered:
            before_as, alias = stripped[5:].split(" as ", 1)
            ctx_expr = self._transform_expr(before_as.strip())
            alias_name = alias.strip()
            self._validate_name(alias_name, line)
            return f"with {ctx_expr} as {alias_name}:", True

        if lowered.startswith("for each ") and " in " in lowered:
            rest = stripped[9:]
            var_part, expr_part = rest.split(" in ", 1)
            var_name = var_part.strip()
            expr = self._transform_expr(expr_part.strip())
            self._validate_name(var_name, line)
            return f"for {var_name} in {expr}:", True

        if lowered.startswith("repeat "):
            body = stripped[7:].strip()
            if " as " in body:
                count_expr, var_name = body.split(" as ", 1)
                var = var_name.strip()
                self._validate_name(var, line)
                count = self._transform_expr(count_expr.strip())
                self._validate_expr(count, line)
                return f"for {var} in range({count}):", True
            count = self._transform_expr(body)
            self._validate_expr(count, line)
            return f"for _ in range({count}):", True

        # Simple statements
        if lowered.startswith("say formatted "):
            fmt = stripped[len("say formatted "):].strip()
            py_expr = f"f{fmt}" if not fmt.startswith("f") else fmt
            self._validate_expr(py_expr, line)
            return f"print({py_expr})", False

        if lowered.startswith("say "):
            payload = stripped[4:].strip()
            if payload.startswith('"""'):
                # multi-line literal stays as-is
                py_expr = payload
                self._validate_expr(py_expr, line)
                return f"print({py_expr})", False

            # Validate each argument individually so mixing text/numbers works naturally.
            split_args = self._split_args(payload)

            # If commas are absent, also support string + number + string style concatenations.
            if len(split_args) == 1:
                concat_parts = self._split_concat_args(payload)
                if len(concat_parts) > 1 and any(self._looks_like_string(p) for p in concat_parts):
                    split_args = concat_parts

            parts: List[str] = []
            for part in split_args:
                expr = self._transform_expr(part.strip())
                self._validate_expr(expr, line)
                parts.append(expr)

            py_expr = ", ".join(parts)
            return f"print({py_expr})", False

        if lowered.startswith("ask "):
            body = stripped[4:].strip()
            if not body:
                raise TaleSyntaxError(f"I could not understand: {line.strip()}")

            # ask "Prompt" as var  -> print prompt then read input into var (and result)
            if " as " in body:
                prompt_part, var_part = body.split(" as ", 1)
                prompt_expr = self._transform_expr(prompt_part.strip())
                self._validate_expr(prompt_expr, line)
                var_name = var_part.strip()
                self._validate_name(var_name, line)
                return (
                    f"print({prompt_expr}, end=''); {var_name} = input_provider(); result = {var_name}",
                    False,
                )

            # ask name -> read input into name (and result)
            if re.match(r"^[A-Za-z_][\w]*$", body):
                self._validate_name(body, line)
                return f"{body} = input_provider(); result = {body}", False

            # ask "Prompt" -> print prompt then store input in result
            prompt_expr = self._transform_expr(body)
            self._validate_expr(prompt_expr, line)
            return f"print({prompt_expr}, end=''); result = input_provider()", False

        if lowered.startswith("return"):
            tail = stripped[6:].strip()
            if not tail:
                return "return", False
            expr = self._transform_expr(tail)
            self._validate_expr(expr, line)
            return f"return {expr}", False

        if lowered.startswith("yield"):
            tail = stripped[5:].strip()
            expr = self._transform_expr(tail) if tail else "None"
            self._validate_expr(expr, line)
            return f"yield {expr}", False

        if lowered.startswith("raise"):
            tail = stripped[5:].strip()
            expr = self._transform_expr(tail) if tail else "Exception()"
            self._validate_expr(expr, line)
            return f"raise {expr}", False

        if lowered.startswith("import "):
            return stripped, False

        if lowered.startswith("from "):
            return stripped, False

        if lowered.startswith("global "):
            return stripped, False

        # File handling
        if lowered.startswith("open ") and " as " in lowered:
            before_as, alias = stripped[5:].split(" as ", 1)
            file_expr = self._transform_expr(before_as.strip())
            alias_name = alias.strip()
            self._validate_name(alias_name, line)
            return f"{alias_name} = _open_file({file_expr}, 'r')", False

        if lowered.startswith("write "):
            # write f "text"
            body = stripped[6:]
            match = re.match(r"(\S+)\s+(.+)", body)
            if not match:
                raise TaleSyntaxError(f"Wrong number of values: {line.strip()}")
            target, content = match.group(1), match.group(2)
            expr_target = self._transform_expr(target)
            expr_content = self._transform_expr(content)
            return f"{expr_target}.write({expr_content})", False

        if lowered.startswith("append "):
            body = stripped[7:]
            match = re.match(r"(\S+)\s+(.+)", body)
            if not match:
                raise TaleSyntaxError(f"Wrong number of values: {line.strip()}")
            target, content = match.group(1), match.group(2)
            expr_target = self._transform_expr(target)
            expr_content = self._transform_expr(content)
            return f"{expr_target}.write({expr_content})", False

        if lowered.startswith("read "):
            expr = self._transform_expr(stripped[5:].strip())
            return f"{expr}.read()", False

        if lowered.startswith("close "):
            expr = self._transform_expr(stripped[6:].strip())
            return f"{expr}.close()", False

        # Collections helpers
        if lowered.startswith("add ") and " to " in lowered:
            item, target = stripped[4:].split(" to ", 1)
            expr_item = self._transform_expr(item.strip())
            target_name = target.strip()
            self._validate_name(target_name, line)
            # Allow both list-style append and numeric/string addition in a single construct.
            return f"{target_name} = _add_to({target_name}, {expr_item})", False

        if lowered.startswith("extend ") and " with " in lowered:
            target, rest = stripped[7:].split(" with ", 1)
            target_name = target.strip()
            expr = self._transform_expr(rest.strip())
            self._validate_name(target_name, line)
            return f"{target_name}.extend({expr})", False

        if lowered.startswith("insert ") and " into " in lowered and " at " in lowered:
            value_part, rest = stripped[7:].split(" into ", 1)
            list_part, idx_part = rest.split(" at ", 1)
            list_name = list_part.strip()
            idx_expr = self._transform_expr(idx_part.strip())
            val_expr = self._transform_expr(value_part.strip())
            self._validate_name(list_name, line)
            return f"{list_name}.insert({idx_expr}, {val_expr})", False

        if lowered.startswith("remove ") and " from " in lowered:
            value_part, list_part = stripped[7:].split(" from ", 1)
            list_name = list_part.strip()
            val_expr = self._transform_expr(value_part.strip())
            self._validate_name(list_name, line)
            return f"{list_name}.remove({val_expr})", False

        if lowered.startswith("clear "):
            list_name = stripped[6:].strip()
            return f"{list_name}.clear()", False

        if lowered.startswith("sort "):
            list_name = stripped[5:].strip()
            return f"{list_name}.sort()", False

        if lowered.startswith("reverse "):
            list_name = stripped[8:].strip()
            return f"{list_name}.reverse()", False

        if lowered.startswith("copy "):
            target = stripped[5:].strip()
            expr = self._transform_expr(target)
            return f"({expr}).copy()", False

        if lowered.startswith("get ") and " from " in lowered:
            key_part, dict_part = stripped[4:].split(" from ", 1)
            key_expr = self._transform_expr(key_part.strip())
            dict_expr = self._transform_expr(dict_part.strip())
            return f"{dict_expr}.get({key_expr})", False

        if lowered.startswith("get "):
            body = stripped[4:]
            if " " in body:
                dict_name, key = body.split(" ", 1)
                dict_expr = self._transform_expr(dict_name.strip())
                raw_key = key.strip()
                if re.match(r"^[A-Za-z_][\w]*$", raw_key):
                    key_expr = repr(raw_key)
                else:
                    key_expr = self._transform_expr(raw_key)
                return f"{dict_expr}.get({key_expr})", False

        if lowered.startswith("set ") and " to " in lowered:
            body = stripped[4:]
            before_to, value_part = body.split(" to ", 1)
            if " " in before_to:
                dict_name, key_part = before_to.split(" ", 1)
                dict_expr = self._transform_expr(dict_name.strip())
                key_expr = self._transform_expr(key_part.strip())
                val_expr = self._transform_expr(value_part.strip())
                return f"{dict_expr}[{key_expr}] = {val_expr}", False

        if lowered.startswith("keys "):
            dict_expr = self._transform_expr(stripped[5:].strip())
            return f"list({dict_expr}.keys())", False

        if lowered.startswith("values "):
            dict_expr = self._transform_expr(stripped[7:].strip())
            return f"list({dict_expr}.values())", False

        if lowered.startswith("items "):
            dict_expr = self._transform_expr(stripped[6:].strip())
            return f"list({dict_expr}.items())", False

        if lowered.startswith("pop ") and " " in stripped:
            body = stripped[4:]
            if " " in body:
                dict_name, key_part = body.split(" ", 1)
                dict_expr = self._transform_expr(dict_name.strip())
                key_expr = self._transform_expr(key_part.strip())
                return f"{dict_expr}.pop({key_expr}, None)", False

        if lowered.startswith("pop "):
            list_name = stripped[4:].strip()
            return f"{list_name}.pop()", False

        if lowered.startswith("unpack ") and " into " in lowered:
            value_part, target_part = stripped[7:].split(" into ", 1)
            value_expr = self._transform_expr(value_part.strip())
            targets = target_part.strip()
            return f"{targets} = {value_expr}", False

        if lowered in {"break", "continue", "pass"}:
            return lowered, False

        # Explicit list declaration, e.g., "list nums is [1,2,3]" or "list nums"
        if lowered.startswith("list "):
            body = stripped[5:].strip()
            if " is " in body:
                name_part, expr_part = body.split(" is ", 1)
                expr = self._transform_expr(expr_part.strip())
            else:
                name_part, expr = body, "[]"
            var = name_part.strip()
            self._validate_name(var, line)
            self._validate_expr(expr, line)
            return f"{var} = {expr}", False

        # Explicit dict declaration, e.g., "dict user is {name:"Alex"}" or "dict user"
        if lowered.startswith("dict "):
            body = stripped[5:].strip()
            if " is " in body:
                name_part, expr_part = body.split(" is ", 1)
                expr = self._transform_expr(expr_part.strip())
            else:
                name_part, expr = body, "{}"
            var = name_part.strip()
            self._validate_name(var, line)
            self._validate_expr(expr, line)
            return f"{var} = {expr}", False

        # Assignment using "is"
        if " is " in lowered:
            var_name, expr_part = stripped.split(" is ", 1)
            var = var_name.strip()
            self._validate_name(var, line)
            expr = self._transform_expr(expr_part.strip())
            self._validate_expr(expr, line)
            return f"{var} = {expr}", False

        # Fall back: expression-only line
        expr = self._transform_expr(stripped)
        self._validate_expr(expr, line)
        return expr, False

        raise TaleSyntaxError(f"I could not understand: {line.strip()}")

    def _parse_fn_header(self, header: str, line: str) -> Tuple[str, str]:
        parts = header.split()
        if not parts:
            raise TaleSyntaxError(f"I could not understand: {line.strip()}")
        name = parts[0]
        if name == "init":
            name = "__init__"
        params = " ".join(parts[1:])
        params = params.replace(",", " ").replace("  ", " ").strip()
        params = ", ".join([p for p in params.split() if p])
        self._validate_name(name, line)
        return name, params

    def _split_args(self, text: str) -> List[str]:
        # Split by commas respecting simple quotes
        parts: List[str] = []
        current = []
        in_str = False
        quote_char = ''
        for char in text:
            if char in {'"', "'"}:
                if in_str and char == quote_char:
                    in_str = False
                elif not in_str:
                    in_str = True
                    quote_char = char
            if char == "," and not in_str:
                parts.append("".join(current))
                current = []
            else:
                current.append(char)
        if current:
            parts.append("".join(current))
        return parts

    def _split_concat_args(self, text: str) -> List[str]:
        """Split by top-level plus signs while respecting quotes/brackets."""
        parts: List[str] = []
        current: List[str] = []
        in_str = False
        quote_char = ''
        depth = 0

        for char in text:
            if char in {'"', "'"}:
                if in_str and char == quote_char:
                    in_str = False
                elif not in_str:
                    in_str = True
                    quote_char = char
            elif not in_str:
                if char in "([{":
                    depth += 1
                elif char in ")]}":
                    depth = max(0, depth - 1)

            if char == "+" and not in_str and depth == 0:
                parts.append("".join(current))
                current = []
            else:
                current.append(char)

        if current:
            parts.append("".join(current))
        return parts

    def _looks_like_string(self, text: str) -> bool:
        trimmed = text.strip()
        if len(trimmed) >= 3 and trimmed.startswith('"""'):
            return trimmed.endswith('"""')
        if len(trimmed) >= 2 and trimmed[0] == trimmed[-1] and trimmed[0] in {'"', "'"}:
            return True
        return False

    def _split_first(self, text: str) -> Tuple[str, str]:
        parts = self._split_args(text)
        if len(parts) < 2:
            ws_parts = text.strip().split(None, 1)
            if len(ws_parts) < 2:
                raise TaleSyntaxError(f"Wrong number of values: {text}")
            return ws_parts[0].strip(), ws_parts[1].strip()
        first = parts[0]
        rest = text[len(first):].lstrip().lstrip(",").strip()
        if not rest:
            rest = parts[1]
        return first.strip(), rest.strip()

    def _normalize_dict(self, expr: str) -> str:
        # Convert name: to "name": inside dict literals
        pattern = r"(?<![\"'])\b(?P<key>[A-Za-z_][\w]*)\s*:"
        return re.sub(pattern, r'"\g<key>":', expr)

    def _transform_expr(self, expr: str) -> str:
        expr = expr.strip()

        # If it's a plain string literal, return as-is so we don't mis-handle colons inside.
        if self._looks_like_string(expr):
            return expr

        if expr.startswith("type of "):
            return f"type({self._transform_expr(expr[8:].strip())})"
        if expr.startswith("id of "):
            return f"id({self._transform_expr(expr[6:].strip())})"
        if expr.startswith('text r"') or expr.startswith("text r'"):
            return expr[5:].strip()

        # String helpers
        unary_str = {
            "upper ": ".upper()",
            "lower ": ".lower()",
            "title ": ".title()",
            "strip ": ".strip()",
            "isalpha ": ".isalpha()",
            "isdigit ": ".isdigit()",
            "isalnum ": ".isalnum()",
        }
        for prefix, suffix in unary_str.items():
            if expr.startswith(prefix):
                tail = expr[len(prefix):].strip()
                if tail.startswith("of "):
                    tail = tail[3:].strip()
                base = self._transform_expr(tail)
                return f"({base}){suffix}"

        if expr.startswith("replace "):
            match = re.match(r'replace\s+(.+?)\s+"([^"]*)"\s+"([^"]*)"', expr)
            if match:
                base = self._transform_expr(match.group(1).strip())
                old = match.group(2)
                new = match.group(3)
                return f"({base}).replace(\"{old}\", \"{new}\")"

        if expr.startswith("split "):
            match = re.match(r'split\s+(.+?)\s+(.+)$', expr)
            if match:
                base = self._transform_expr(match.group(1).strip())
                sep = self._transform_expr(match.group(2).strip())
                return f"({base}).split({sep})"

        if expr.startswith("join "):
            match = re.match(r'join\s+(.+?)\s+(.+)$', expr)
            if match:
                glue = self._transform_expr(match.group(1).strip())
                target = self._transform_expr(match.group(2).strip())
                return f"({glue}).join({target})"

        if expr.startswith("find "):
            match = re.match(r'find\s+(.+?)\s+(.+)$', expr)
            if match:
                base = self._transform_expr(match.group(1).strip())
                sub = self._transform_expr(match.group(2).strip())
                return f"({base}).find({sub})"

        if expr.startswith("count "):
            # Allow `count > 0` style comparisons by skipping the helper when the next token is an operator.
            if not re.match(r"count\s*[><=]", expr):
                match = re.match(r'count\s+(.+?)\s+(.+)$', expr)
                if match:
                    base = self._transform_expr(match.group(1).strip())
                    sub = self._transform_expr(match.group(2).strip())
                    return f"({base}).count({sub})"

        if expr.startswith("starts "):
            match = re.match(r'starts\s+(.+?)\s+(.+)$', expr)
            if match:
                base = self._transform_expr(match.group(1).strip())
                sub = self._transform_expr(match.group(2).strip())
                return f"({base}).startswith({sub})"

        if expr.startswith("ends "):
            match = re.match(r'ends\s+(.+?)\s+(.+)$', expr)
            if match:
                base = self._transform_expr(match.group(1).strip())
                sub = self._transform_expr(match.group(2).strip())
                return f"({base}).endswith({sub})"

        # Map/filter helpers
        if expr.startswith("map "):
            _, rest = expr.split(" ", 1)
            fn_part, seq_part = self._split_first(rest)
            return f"map({self._transform_expr(fn_part)}, {self._transform_expr(seq_part)})"

        if expr.startswith("filter "):
            _, rest = expr.split(" ", 1)
            fn_part, seq_part = self._split_first(rest)
            return f"filter({self._transform_expr(fn_part)}, {self._transform_expr(seq_part)})"

        if expr.startswith("enumerate "):
            return f"enumerate({self._transform_expr(expr[10:].strip())})"

        if expr.startswith("zip "):
            parts = [self._transform_expr(p.strip()) for p in self._split_args(expr[4:])]
            return f"zip({', '.join(parts)})"

        if expr.startswith("next "):
            return f"next({self._transform_expr(expr[5:].strip())})"

        # Explicit call helper: "call foo" or "call foo 1 2"
        if expr.startswith("call "):
            body = expr[5:].strip()
            if not body:
                raise TaleSyntaxError("I could not understand: call")
            # If user already wrote parentheses, just transform as a normal expr.
            if "(" in body:
                return self._transform_expr(body)
            try:
                parts = shlex.split(body, posix=False)
            except ValueError:
                parts = body.split()
            fn_name, *arg_parts = parts
            if not re.match(r"^[A-Za-z_][\w]*$", fn_name):
                raise TaleSyntaxError(f"I could not understand: {expr}")
            if not arg_parts:
                return f"{fn_name}()"
            arg_exprs = [self._transform_expr(p) for p in arg_parts]
            return f"{fn_name}({', '.join(arg_exprs)})"

        # Dictionary get helper inside expressions: "get user name" -> user.get("name")
        if expr.startswith("get "):
            body = expr[4:].strip()
            if " " in body:
                dict_name, key = body.split(" ", 1)
                dict_expr = self._transform_expr(dict_name.strip())
                raw_key = key.strip()
                if re.match(r"^[A-Za-z_][\w]*$", raw_key):
                    key_expr = repr(raw_key)
                else:
                    key_expr = self._transform_expr(raw_key)
                return f"({dict_expr}).get({key_expr})"

        if expr.startswith("len "):
            return f"len({self._transform_expr(expr[4:].strip())})"

        if expr.startswith("sum "):
            return f"sum({self._transform_expr(expr[4:].strip())})"

        if expr.startswith("min "):
            return f"min({self._transform_expr(expr[4:].strip())})"

        if expr.startswith("max "):
            return f"max({self._transform_expr(expr[4:].strip())})"

        if expr.startswith("sorted "):
            return f"sorted({self._transform_expr(expr[7:].strip())})"

        if expr.startswith("any "):
            return f"any({self._transform_expr(expr[4:].strip())})"

        if expr.startswith("all "):
            return f"all({self._transform_expr(expr[4:].strip())})"

        # Set operations
        if expr.startswith("union "):
            a, b = self._split_first(expr[6:])
            return f"({self._transform_expr(a)}) | ({self._transform_expr(b)})"

        if expr.startswith("intersection "):
            a, b = self._split_first(expr[13:])
            return f"({self._transform_expr(a)}) & ({self._transform_expr(b)})"

        if expr.startswith("difference "):
            a, b = self._split_first(expr[11:])
            return f"({self._transform_expr(a)}) - ({self._transform_expr(b)})"

        if expr.startswith("subset "):
            a, b = self._split_first(expr[7:])
            return f"({self._transform_expr(a)}).issubset({self._transform_expr(b)})"

        if expr.startswith("copy "):
            return f"({self._transform_expr(expr[5:].strip())}).copy()"

        # Dictionary helpers
        if expr.startswith("dict "):
            # allow "dict name is { ... }" handled earlier; here treat as literal
            return self._normalize_dict(expr[5:])

        # JSON / CSV helpers
        if expr.startswith("json read "):
            path_expr = self._transform_expr(expr[10:].strip())
            return f"read_json({path_expr})"
        if expr.startswith("json write ") and " to " in expr:
            body = expr[11:]
            data_part, path_part = body.split(" to ", 1)
            data_expr = self._transform_expr(data_part.strip())
            path_expr = self._transform_expr(path_part.strip())
            return f"write_json({data_expr}, {path_expr})"
        if expr.startswith("csv read "):
            path_expr = self._transform_expr(expr[9:].strip())
            return f"read_csv({path_expr})"
        if expr.startswith("csv write ") and " to " in expr:
            body = expr[10:]
            rows_part, path_part = body.split(" to ", 1)
            rows_expr = self._transform_expr(rows_part.strip())
            path_expr = self._transform_expr(path_part.strip())
            return f"write_csv({rows_expr}, {path_expr})"

        if expr.startswith("read "):
            return f"({self._transform_expr(expr[5:].strip())}).read()"

        # Lambda arrow syntax
        if expr.startswith("lambda ") and "->" in expr:
            params, body = expr[7:].split("->", 1)
            return f"lambda {params.strip()}: {self._transform_expr(body.strip())}"

        # Space-separated call shorthand: "add 5 7" -> "add(5, 7)" when safe.
        if re.match(r"^[A-Za-z_][\w]*\s", expr) and not any(op in expr for op in "+-*/%<>=:()[]{}.,"):
            try:
                parts = shlex.split(expr, posix=False)  # keep quotes intact for string args
            except ValueError:
                parts = expr.split()
            if len(parts) > 1:
                fn_name, arg_parts = parts[0], parts[1:]
                if re.match(r"^[A-Za-z_][\w]*$", fn_name):
                    arg_exprs = [self._transform_expr(p) for p in arg_parts]
                    return f"{fn_name}({', '.join(arg_exprs)})"

        # Comprehension and slices already look like Python; normalize keywords
        expr = self._normalize_dict(expr)
        expr = re.sub(r"\btrue\b", "True", expr, flags=re.IGNORECASE)
        expr = re.sub(r"\bfalse\b", "False", expr, flags=re.IGNORECASE)
        expr = re.sub(r"\bnothing\b", "None", expr, flags=re.IGNORECASE)
        expr = re.sub(r"\bnone\b", "None", expr, flags=re.IGNORECASE)
        expr = re.sub(r"\bis not same as\b", " != ", expr, flags=re.IGNORECASE)
        expr = re.sub(r"\bis same as\b", " == ", expr, flags=re.IGNORECASE)

        # number/text/decimal conversions
        expr = re.sub(r"\bnumber\(", "int(", expr)
        expr = re.sub(r"\btext\(", "str(", expr)
        expr = re.sub(r"\bdecimal\(", "float(", expr)

        return expr

    def _validate_name(self, name: str, line: str) -> None:
        if not name or not re.match(r"^[A-Za-z_][\w]*$", name):
            raise TaleSyntaxError(f"I could not understand: {line.strip()}")

    def _validate_expr(self, expr: str, line: str) -> None:
        try:
            tree = ast.parse(expr, mode="eval")
        except SyntaxError:
            raise TaleSyntaxError(f"I could not understand: {line.strip()}")

        allowed = (
            ast.Expression,
            ast.BinOp,
            ast.UnaryOp,
            ast.BoolOp,
            ast.Compare,
            ast.Call,
            ast.Name,
            ast.Constant,
            ast.Load,
            ast.Add,
            ast.Sub,
            ast.Mult,
            ast.Div,
            ast.Mod,
            ast.FloorDiv,
            ast.Pow,
            ast.And,
            ast.Or,
            ast.Not,
            ast.USub,
            ast.UAdd,
            ast.Eq,
            ast.NotEq,
            ast.Lt,
            ast.LtE,
            ast.Gt,
            ast.GtE,
            ast.List,
            ast.Tuple,
            ast.Dict,
            ast.Set,
            ast.ListComp,
            ast.DictComp,
            ast.SetComp,
            ast.GeneratorExp,
            ast.comprehension,
            ast.IfExp,
            ast.Subscript,
            ast.Slice,
            ast.Attribute,
            ast.Lambda,
        )

        for node in ast.walk(tree):
            if not isinstance(node, allowed):
                raise TaleSyntaxError(f"I could not understand: {line.strip()}")


def _open_file(path: str, mode: str = "r"):
    return open(path, mode, encoding="utf-8", newline="")


def _add_to(target, value):  # noqa: ANN001
    """Append when possible; otherwise, use additive update."""
    if hasattr(target, "append"):
        target.append(value)
        return target
    try:
        return target + value
    except Exception as exc:  # noqa: BLE001
        raise TypeError(f"Cannot add to {type(target).__name__}: {exc}")


def read_json(path: str):
    with _open_file(path, "r") as fh:
        return json.load(fh)


def write_json(data, path: str):
    with _open_file(path, "w") as fh:
        return json.dump(data, fh, indent=2)


def read_csv(path: str):
    with _open_file(path, "r") as fh:
        return [row for row in csv.reader(fh)]


def write_csv(rows, path: str):
    with _open_file(path, "w") as fh:
        writer = csv.writer(fh)
        for row in rows:
            writer.writerow(row)
        return rows


def _build_safe_builtins():
    allowed_imports = {"math", "random", "datetime", "json", "csv", "os", "sys"}

    def safe_import(name, globals=None, locals=None, fromlist=None, level=0):  # noqa: ANN001
        if name.split(".")[0] not in allowed_imports:
            raise ImportError(f"Import not allowed: {name}")
        return __import__(name, globals, locals, fromlist, level)

    safe = {
        "__import__": safe_import,
        "abs": abs,
        "all": all,
        "any": any,
        "bool": bool,
        "dict": dict,
        "enumerate": enumerate,
        "filter": filter,
        "float": float,
        "int": int,
        "len": len,
        "list": list,
        "map": map,
        "max": max,
        "min": min,
        "next": next,
        "print": print,
        "range": range,
        "round": round,
        "set": set,
        "sorted": sorted,
        "str": str,
        "sum": sum,
        "tuple": tuple,
        "zip": zip,
        "open": _open_file,
        "id": id,
        "type": type,
        "Exception": Exception,
    }
    return safe


def run_tale_code(code: str, inputs: Optional[List[str]] = None) -> Dict[str, object]:
    interpreter = TaleInterpreter(code, inputs)

    try:
        python_code = interpreter.to_python()
    except TaleSyntaxError as exc:
        return {
            "ok": False,
            "error": str(exc),
            "suggestedFix": "I could not understand the TALE syntax; check if/else/end, assignments, and helpers.",
            "translated": None,
            "tale": code,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": f"I could not understand: {exc}",
            "suggestedFix": "Ensure TALE lines follow the documented patterns.",
            "translated": None,
            "tale": code,
        }

    output_buffer = io.StringIO()

    def _safe_print(*args, **kwargs):  # noqa: ANN001
        print(*args, **kwargs, file=output_buffer)

    safe_builtins = _build_safe_builtins()
    safe_globals = {
        "__builtins__": safe_builtins,
        "__name__": "__main__",
        "input_provider": interpreter.input_provider,
        "print": _safe_print,
        "math": math,
        "random": random,
        "datetime": datetime,
        "json": json,
        "csv": csv,
        "os": os,
        "sys": sys,
        "read_json": read_json,
        "write_json": write_json,
        "read_csv": read_csv,
        "write_csv": write_csv,
        "_open_file": _open_file,
        "_add_to": _add_to,
    }
    exec_env: dict = dict(safe_globals)

    try:
        with redirect_stdout(output_buffer):
            exec(python_code, exec_env, exec_env)
    except NameError as exc:
        return {
            "ok": False,
            "error": f"Unknown variable: {exc}",
            "suggestedFix": "Did you define the variable before using it?",
            "translated": python_code,
            "tale": code,
        }
    except InputExhausted as exc:
        return {
            "ok": False,
            "error": str(exc),
            "suggestedFix": "Provide an input value for each `ask` line in the Inputs box before running.",
            "translated": python_code,
            "tale": code,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": str(exc),
            "suggestedFix": "Check the translated Python to see what went wrong.",
            "translated": python_code,
            "tale": code,
        }

    return {
        "ok": True,
        "output": output_buffer.getvalue(),
        "translated": python_code,
        "tale": code,
    }


def analyze_tale_code(code: str) -> Dict[str, object]:
    interpreter = TaleInterpreter(code, [])
    try:
        interpreter.to_python()
        return {"ok": True, "diagnostics": []}
    except TaleSyntaxError as exc:
        line_no = None
        msg = str(exc)
        match = re.match(r"Line (\d+):", msg)
        if match:
            line_no = int(match.group(1))
        return {"ok": False, "diagnostics": [{"line": line_no, "message": msg}]}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "diagnostics": [{"line": None, "message": f"Unknown error: {exc}"}]}
