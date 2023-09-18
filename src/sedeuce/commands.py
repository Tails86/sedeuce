# MIT License
#
# Copyright (c) 2023 James Smith
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from .conditions import *
from .utils import *

import re
import subprocess
from io import IOBase
from typing import Any, Union, List

class SedCommand:
    def __init__(self, condition:SedCondition) -> None:
        self._condition = condition
        self.label:str = None

    def handle(self, dat:WorkingData) -> None:
        if self._condition is None or self._condition.is_match(dat):
            self._handle(dat)

    def _handle(self, dat:WorkingData) -> None:
        pass

def _run_command(cmd):
    proc_output = subprocess.run(
        cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out_dat = proc_output.stdout
    if out_dat.endswith(b'\n'):
        out_dat = out_dat[:-1]
    if out_dat.endswith(b'\r'):
        out_dat = out_dat[:-1]
    return out_dat

class SubstituteCommand(SedCommand):
    COMMAND_CHAR = 's'

    def __init__(self, condition:SedCondition, find_pattern:Union[bytes,str], replace_pattern:Union[bytes,str]):
        super().__init__(condition)
        find_pattern = find_pattern
        if isinstance(find_pattern, str):
            find_pattern = find_pattern.encode()
        # TODO: The $ character should correspond to only the end of the pattern space,
        #       even if multiple newlines are included
        self._find_bytes = find_pattern
        self._only_first_match = self._find_bytes.startswith(b'^')
        # TODO: implement special sequences using replace callback instead?
        self._replace = replace_pattern
        if isinstance(self._replace, str):
            self._replace = self._replace.encode()

        self.global_replace:bool = False
        self.nth_match:Union[int,None] = None
        self.print_matched_lines:bool = False
        self.matched_file:Union[IOBase,None] = None
        self.execute_replacement:bool = False
        self._ignore_case = False
        # This gives a bit different implementation within re
        self._multiline_mode = False
        self._extended_regex = True

        self._compile_find()

    @property
    def ignore_case(self) -> bool:
        return self._ignore_case

    @ignore_case.setter
    def ignore_case(self, ignore_case:bool):
        if self._ignore_case != ignore_case:
            self._ignore_case = ignore_case
            # Need to recompile find
            self._compile_find()

    @property
    def multiline_mode(self) -> bool:
        return self._multiline_mode

    @multiline_mode.setter
    def multiline_mode(self, multiline_mode:bool):
        if self._multiline_mode != multiline_mode:
            self._multiline_mode = multiline_mode
            # Need to recompile find
            self._compile_find()

    def _compile_find(self) -> None:
        flags = 0
        if self._ignore_case:
            flags |= re.IGNORECASE
        self._find = re.compile(self._find_bytes, flags)

    def _match_made(self, dat:WorkingData) -> None:
        if self.print_matched_lines:
            dat.print_bytes(dat.pattern_space)
        if self.matched_file is not None:
            self.matched_file.write(dat.pattern_space)
            self.matched_file.flush()

    def _handle(self, dat:WorkingData) -> None:
        if dat.extended_regex != self._extended_regex:
            self._find_bytes = pattern_escape_invert(self._find_bytes, '+?|{}()')
            self._compile_find()
            self._extended_regex = not self._extended_regex
        # Determine what nth match is based on self data
        nth_match = self.nth_match
        if self._only_first_match:
            if self.nth_match is not None:
                if (self.nth_match == 0 and not self.global_replace) or self.nth_match > 1:
                    # No way to ever match this
                    return
                else:
                    # Only first match is valid
                    nth_match = 1

        if nth_match is None and not self.global_replace:
            nth_match = 1

        # This is a pain in the ass - manually go to each match in order to handle all features
        match_idx = 0
        offset = 0
        next_chunk = dat.pattern_space
        match = re.search(self._find, next_chunk)
        matched = False
        while match:
            start = match.start(0) + offset
            end = match.end(0) + offset
            if nth_match is None or (match_idx + 1) >= nth_match:
                matched = True
                new_str = re.sub(self._find, self._replace, match.group(0))
                if self.execute_replacement:
                    # Execute the replacement
                    new_dat = _run_command(new_str.decode())
                else:
                    new_dat = new_str
                dat.pattern_space = dat.pattern_space[0:start] + new_dat + dat.pattern_space[end:]
                if nth_match is not None and not self.global_replace:
                    # All done
                    break
                offset = start + len(new_dat)
            else:
                offset = end

            if start == end:
                # Need to advance to prevent infinite loop
                offset += 1
            # If we matched while the previous chunk was empty, exit now to prevent infinite loop
            if not next_chunk:
                break
            next_chunk = dat.pattern_space[offset:]
            match = re.search(self._find, next_chunk)
            match_idx += 1
        if matched:
            self._match_made(dat)
        return

    @staticmethod
    def from_string(condition:SedCondition, s:Union[str,StringParser], sandbox_mode:bool=False) -> SedCommand:
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            s.advance(1)
            find_pattern, replace_pattern = dual_field_command_parse(s)

            if find_pattern is None or replace_pattern is None:
                raise SedParsingException('unterminated `s\' command')

            command = SubstituteCommand(condition, find_pattern, replace_pattern)

            while s.advance_past() and s[0] not in SOMETIMES_END_CMD_CHARS:
                c = s[0]
                s.mark()
                s.advance(1)
                if c in NUMBER_CHARS:
                    s.advance_past(NUMBER_CHARS)
                    command.nth_match = int(s.str_from_mark())
                elif c == 'g':
                    command.global_replace = True
                elif c == 'p':
                    command.print_matched_lines = True
                elif c == 'w':
                    if sandbox_mode:
                        raise SedParsingException('e/r/w commands disabled in sandbox mode')
                    s.mark()
                    s.advance_end() # Used the rest of the characters here, including end command chars
                    file_name = s.str_from_mark().strip()
                    command.matched_file = filename_to_writer(file_name)
                elif c == 'e':
                    if sandbox_mode:
                        raise SedParsingException('e/r/w commands disabled in sandbox mode')
                    command.execute_replacement = True
                elif c == 'i' or c == 'I':
                    command.ignore_case = True
                elif c == 'm' or c == 'M':
                    command.multiline_mode = True
                # else: ignore

            return command
        else:
            raise SedParsingException('Not a substitute sequence')

class AppendCommand(SedCommand):
    COMMAND_CHAR = 'a'

    def __init__(self, condition: SedCondition, append_value:Union[bytes,str]):
        super().__init__(condition)
        if isinstance(append_value, str):
            self._append_value = append_value.encode()
        else:
            self._append_value = append_value

    def _handle(self, dat:WorkingData) -> None:
        dat.append(self._append_value)

    @staticmethod
    def from_string(condition:SedCondition, s:Union[str,StringParser], sandbox_mode:bool=False) -> SedCommand:
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            s.advance(1)
            if len(s) > 0 and s[0] == '\\':
                s.advance(1)
            else:
                s.advance_past()
            s.mark()
            # Semicolons are considered part of the append string
            s.advance_end()
            return AppendCommand(condition, s.str_from_mark())
        else:
            raise SedParsingException('Not an append sequence')

class BranchCommand(SedCommand):
    COMMAND_CHAR = 'b'

    def __init__(self, condition: SedCondition, branch_name:str=''):
        super().__init__(condition)
        self._branch_name = branch_name

    def _handle(self, dat:WorkingData) -> None:
        if self._branch_name:
            dat.jump_to = self._branch_name

    @staticmethod
    def from_string(condition:SedCondition, s:Union[str,StringParser], sandbox_mode:bool=False) -> SedCommand:
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            s.advance(1)
            s.advance_past()
            s.mark()
            s.advance_until(SOMETIMES_END_CMD_CHARS)
            branch_name = s.str_from_mark()
            return BranchCommand(condition, branch_name)
        else:
            raise SedParsingException('Not a branch sequence')

class ReplaceCommand(SedCommand):
    COMMAND_CHAR = 'c'

    def __init__(self, condition: SedCondition, replace:Union[bytes,str]):
        super().__init__(condition)
        if isinstance(replace, str):
            self._replace = replace.encode()
        else:
            self._replace = replace

    def _handle(self, dat:WorkingData) -> None:
        add_newline = dat.pattern_space.endswith(dat.newline)
        dat.pattern_space = self._replace
        if add_newline:
            dat.pattern_space += dat.newline
        return

    @staticmethod
    def from_string(condition:SedCondition, s:Union[str,StringParser], sandbox_mode:bool=False) -> SedCommand:
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            s.advance(1)
            if len(s) > 0 and s[0] == '\\':
                s.advance(1)
            else:
                s.advance_past()
            s.mark()
            # Semicolons are considered part of the replace string
            s.advance_end()
            replace = s.str_from_mark()
            return ReplaceCommand(condition, replace)
        else:
            raise SedParsingException('Not a replace sequence')

class DeleteCommand(SedCommand):
    COMMAND_CHAR = 'd'

    def __init__(self, condition:SedCondition):
        super().__init__(condition)

    def _handle(self, dat:WorkingData) -> None:
        dat.pattern_space = b''
        # Jump to end
        dat.jump_to = -1

    @staticmethod
    def from_string(condition:SedCondition, s:Union[str,StringParser], sandbox_mode:bool=False) -> SedCommand:
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            s.advance(1)
            s.advance_past()
            return DeleteCommand(condition)
        else:
            raise SedParsingException('Not a delete command')

class DeleteToNewlineCommand(SedCommand):
    COMMAND_CHAR = 'D'

    def __init__(self, condition:SedCondition):
        super().__init__(condition)

    def _handle(self, dat:WorkingData) -> None:
        pos = dat.pattern_space.find(dat.newline)
        if pos >= 0:
            dat.pattern_space = dat.pattern_space[pos+1:]
            # jump to beginning
            dat.jump_to = 0
        else:
            dat.pattern_space = b''
            # jump to end
            dat.jump_to = -1

    @staticmethod
    def from_string(condition:SedCondition, s:Union[str,StringParser], sandbox_mode:bool=False) -> SedCommand:
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            s.advance(1)
            s.advance_past()
            return DeleteToNewlineCommand(condition)
        else:
            raise SedParsingException('Not a delete to newline command')

class ExecuteCommand(SedCommand):
    COMMAND_CHAR = 'e'

    def __init__(self, condition: SedCondition, cmd:str=None) -> None:
        super().__init__(condition)
        self.cmd = cmd

    def _handle(self, dat:WorkingData) -> None:
        if self.cmd:
            # Execute the command
            dat.pattern_space = _run_command(self.cmd) + dat.newline + dat.pattern_space
        else:
            # Execute what's in the pattern space and replace the pattern space with the output
            dat.pattern_space = _run_command(dat.pattern_space.decode()) + dat.newline
        return

    @staticmethod
    def from_string(condition:SedCondition, s:Union[str,StringParser], sandbox_mode:bool=False) -> SedCommand:
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            if sandbox_mode:
                raise SedParsingException('e/r/w commands disabled in sandbox mode')
            s.advance(1)
            s.mark()
            # Semicolons are considered part of the execute string
            s.advance_end()
            cmd = s.str_from_mark()
            return ExecuteCommand(condition, cmd)
        else:
            raise SedParsingException('Not an execute sequence')

class FileCommand(SedCommand):
    COMMAND_CHAR = 'F'

    def __init__(self, condition:SedCondition) -> None:
        super().__init__(condition)

    def _handle(self, dat:WorkingData) -> None:
        dat.print_bytes(dat.file_name.encode() + dat.newline)
        return

    @staticmethod
    def from_string(condition:SedCondition, s:Union[str,StringParser], sandbox_mode:bool=False) -> SedCommand:
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            s.advance(1)
            s.advance_past()
            return FileCommand(condition)
        else:
            raise SedParsingException('Not a file sequence')

class SetHoldspaceCommand(SedCommand):
    COMMAND_CHAR = 'h'

    def __init__(self, condition:SedCondition) -> None:
        super().__init__(condition)

    def _handle(self, dat:WorkingData) -> None:
        dat.holdspace = dat.pattern_space
        return

    @staticmethod
    def from_string(condition:SedCondition, s:Union[str,StringParser], sandbox_mode:bool=False) -> SedCommand:
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            s.advance(1)
            s.advance_past()
            return SetHoldspaceCommand(condition)
        else:
            raise SedParsingException('Not a set holdspace sequence')

class AppendHoldspaceCommand(SedCommand):
    COMMAND_CHAR = 'H'

    def __init__(self, condition:SedCondition) -> None:
        super().__init__(condition)

    def _handle(self, dat:WorkingData) -> None:
        holdspace = dat.holdspace
        if not holdspace.endswith(dat.newline):
            holdspace += dat.newline
        dat.holdspace = holdspace + dat.pattern_space
        return

    @staticmethod
    def from_string(condition:SedCondition, s:Union[str,StringParser], sandbox_mode:bool=False) -> SedCommand:
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            s.advance(1)
            s.advance_past()
            return AppendHoldspaceCommand(condition)
        else:
            raise SedParsingException('Not an append holdspace sequence')

class SetFromHoldspaceCommand(SedCommand):
    COMMAND_CHAR = 'g'

    def __init__(self, condition:SedCondition) -> None:
        super().__init__(condition)

    def _handle(self, dat:WorkingData) -> None:
        holdspace = dat.holdspace
        if not holdspace.endswith(dat.newline):
            holdspace += dat.newline
        dat.pattern_space = holdspace
        return

    @staticmethod
    def from_string(condition:SedCondition, s:Union[str,StringParser], sandbox_mode:bool=False) -> SedCommand:
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            s.advance(1)
            s.advance_past()
            return SetFromHoldspaceCommand(condition)
        else:
            raise SedParsingException('Not a set from holdspace sequence')

class AppendFromHoldspaceCommand(SedCommand):
    COMMAND_CHAR = 'G'

    def __init__(self, condition:SedCondition) -> None:
        super().__init__(condition)

    def _handle(self, dat:WorkingData) -> None:
        dat.append(dat.holdspace)

    @staticmethod
    def from_string(condition:SedCondition, s:Union[str,StringParser], sandbox_mode:bool=False) -> SedCommand:
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            s.advance(1)
            s.advance_past()
            return AppendFromHoldspaceCommand(condition)
        else:
            raise SedParsingException('Not an append from holdspace sequence')

class InsertCommand(SedCommand):
    COMMAND_CHAR = 'i'

    def __init__(self, condition:SedCondition, insert_value):
        super().__init__(condition)
        if isinstance(insert_value, str):
            self._insert_value = insert_value.encode()
        else:
            self._insert_value = insert_value

    def _handle(self, dat:WorkingData) -> None:
        dat.insert(self._insert_value)
        return

    @staticmethod
    def from_string(condition:SedCondition, s:Union[str,StringParser], sandbox_mode:bool=False) -> SedCommand:
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            s.advance(1)
            if len(s) > 0 and s[0] == '\\':
                s.advance(1)
            else:
                s.advance_past()
            s.mark()
            # Semicolons are considered part of the append string
            s.advance_end()
            return InsertCommand(condition, s.str_from_mark())
        else:
            raise SedParsingException('Not an insert sequence')

class UnambiguousPrintCommand(SedCommand):
    COMMAND_CHAR = 'l'
    CONVERSION_DICT = {
        ord('\a'): list(b'\\a'),
        ord('\b'): list(b'\\b'),
        ord('\t'): list(b'\\t'),
        ord('\v'): list(b'\\v'),
        ord('\f'): list(b'\\f'),
        ord('\r'): list(b'\\r'),
        ord('\\'): list(b'\\\\')
    }

    def __init__(self, condition:SedCondition) -> None:
        super().__init__(condition)

    @staticmethod
    def _convert_byte(b:int, newline_char:bytes) -> List[int]:
        if b == ord(newline_char):
            return [b]
        elif b in __class__.CONVERSION_DICT:
            return __class__.CONVERSION_DICT[b]
        elif b < 32 or b > 126:
            return list(b'\\' + '{:o}'.format(b).encode())
        else:
            return [b]

    def _handle(self, dat:WorkingData) -> None:
        mod_pattern = dat.pattern_space
        if mod_pattern.endswith(dat.newline):
            mod_pattern = mod_pattern[:-1] + b'$' + dat.newline
        else:
            mod_pattern += b'$'

        the_bytes = None
        cur_len = 0

        for i, b in enumerate(mod_pattern):
            the_bytes = __class__._convert_byte(b, dat.newline)
            if cur_len > 0 and dat.unambiguous_line_len > 0:
                if (
                    cur_len + len(the_bytes) > dat.unambiguous_line_len
                    or ((cur_len + len(the_bytes)) == dat.unambiguous_line_len
                        and i != (len(mod_pattern) - 1))
                ):
                    dat.print_bytes(b'\\' + dat.newline)
                    cur_len = 0
            dat.print_bytes(bytes(the_bytes))
            cur_len += len(the_bytes)

    @staticmethod
    def from_string(condition:SedCondition, s:Union[str,StringParser], sandbox_mode:bool=False) -> SedCommand:
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            s.advance(1)
            s.advance_past()
            return UnambiguousPrintCommand(condition)
        else:
            raise SedParsingException('Not an unambiguous print sequence')

class NextCommand(SedCommand):
    COMMAND_CHAR = 'n'

    def __init__(self, condition:SedCondition) -> None:
        super().__init__(condition)

    def _handle(self, dat:WorkingData) -> None:
        if not dat.next_line():
            raise SedFileCompleteException()

    @staticmethod
    def from_string(condition:SedCondition, s:Union[str,StringParser], sandbox_mode:bool=False) -> SedCommand:
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            s.advance(1)
            s.advance_past()
            return NextCommand(condition)
        else:
            raise SedParsingException('Not a next command sequence')

class AppendNextCommand(SedCommand):
    COMMAND_CHAR = 'N'

    def __init__(self, condition:SedCondition) -> None:
        super().__init__(condition)

    def _handle(self, dat:WorkingData) -> None:
        if not dat.append_next_line():
            raise SedFileCompleteException()

    @staticmethod
    def from_string(condition:SedCondition, s:Union[str,StringParser], sandbox_mode:bool=False) -> SedCommand:
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            s.advance(1)
            s.advance_past()
            return AppendNextCommand(condition)
        else:
            raise SedParsingException('Not an append next command sequence')

class PrintCommand(SedCommand):
    COMMAND_CHAR = 'p'

    def __init__(self, condition:SedCondition) -> None:
        super().__init__(condition)

    def _handle(self, dat:WorkingData) -> None:
        dat.print_bytes(dat.pattern_space)

    @staticmethod
    def from_string(condition:SedCondition, s:Union[str,StringParser], sandbox_mode:bool=False) -> SedCommand:
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            s.advance(1)
            s.advance_past()
            return PrintCommand(condition)
        else:
            raise SedParsingException('Not a print command sequence')

class PrintToNewlineCommand(SedCommand):
    COMMAND_CHAR = 'P'

    def __init__(self, condition:SedCondition) -> None:
        super().__init__(condition)

    def _handle(self, dat:WorkingData) -> None:
        loc = dat.pattern_space.find(dat.newline)
        if loc < 0:
            dat.print_bytes(dat.pattern_space + dat.newline)
        else:
            dat.print_bytes(dat.pattern_space[:loc+1])

    @staticmethod
    def from_string(condition:SedCondition, s:Union[str,StringParser], sandbox_mode:bool=False) -> SedCommand:
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            s.advance(1)
            s.advance_past()
            return PrintToNewlineCommand(condition)
        else:
            raise SedParsingException('Not a print to newline command sequence')

class QuitCommand(SedCommand):
    COMMAND_CHAR = 'q'

    def __init__(self, condition:SedCondition, exit_code=0) -> None:
        super().__init__(condition)
        self.exit_code = exit_code

    def _handle(self, dat:WorkingData) -> None:
        dat.flush_all_data()
        raise SedQuitException(self.exit_code)

    @staticmethod
    def from_string(condition:SedCondition, s:Union[str,StringParser], sandbox_mode:bool=False) -> SedCommand:
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            s.advance(1)
            s.advance_past()
            s.mark()
            s.advance_past(NUMBER_CHARS)
            exit_code_str = s.str_from_mark()
            if exit_code_str:
                return QuitCommand(condition, int(exit_code_str))
            else:
                return QuitCommand(condition)
        else:
            raise SedParsingException('Not a quit command sequence')

class QuitWithoutPrintCommand(SedCommand):
    COMMAND_CHAR = 'Q'

    def __init__(self, condition:SedCondition, exit_code=0) -> None:
        super().__init__(condition)
        self.exit_code = exit_code

    def _handle(self, dat:WorkingData) -> None:
        dat._flush_insert_data() # Only flush insert data before quitting
        raise SedQuitException(self.exit_code)

    @staticmethod
    def from_string(condition:SedCondition, s:Union[str,StringParser], sandbox_mode:bool=False) -> SedCommand:
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            s.advance(1)
            s.advance_past()
            s.mark()
            s.advance_past(NUMBER_CHARS)
            exit_code_str = s.str_from_mark()
            if exit_code_str:
                return QuitWithoutPrintCommand(condition, int(exit_code_str))
            else:
                return QuitWithoutPrintCommand(condition)
        else:
            raise SedParsingException('Not a quit without print command sequence')

class AppendFileContentsCommand(SedCommand):
    COMMAND_CHAR = 'r'

    def __init__(self, condition:SedCondition, file_path:str) -> None:
        super().__init__(condition)
        self.file_path = file_path

    def _handle(self, dat:WorkingData) -> None:
        try:
            with open(self.file_path, 'rb') as fp:
                dat.append(fp.read(), add_newline=False)
        except OSError:
            # Ignore
            pass

    @staticmethod
    def from_string(condition:SedCondition, s:Union[str,StringParser], sandbox_mode:bool=False) -> SedCommand:
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            if sandbox_mode:
                raise SedParsingException('e/r/w commands disabled in sandbox mode')
            s.advance(1)
            s.advance_past()
            s.mark()
            # Semicolons are considered part of the file name string
            s.advance_end()
            return AppendFileContentsCommand(condition, s.str_from_mark())
        else:
            raise SedParsingException('Not an append file contents command sequence')

class AppendLineFromFileCommand(SedCommand):
    COMMAND_CHAR = 'R'

    def __init__(self, condition:SedCondition, file_path:str) -> None:
        super().__init__(condition)
        self._file_path = file_path
        self._file_read = False
        self._file_iter = None

    def _handle(self, dat:WorkingData) -> None:
        if not self._file_read and self._file_iter is None:
            auto_file = AutoInputFileIterable(self._file_path, 'rb', dat.newline)
            try:
                self._file_iter = iter(auto_file)
            except OSError:
                # Ignore file
                self._file_read = True
                self._file_iter = None

        if self._file_iter:
            try:
                next_line = next(self._file_iter)
            except StopIteration:
                self._file_read = True
                self._file_iter = None
            else:
                dat.append(next_line, add_newline=False)

    @staticmethod
    def from_string(condition:SedCondition, s:Union[str,StringParser], sandbox_mode:bool=False) -> SedCommand:
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            if sandbox_mode:
                raise SedParsingException('e/r/w commands disabled in sandbox mode')
            s.advance(1)
            s.advance_past()
            s.mark()
            # Semicolons are considered part of the file name string
            s.advance_end()
            return AppendLineFromFileCommand(condition, s.str_from_mark())
        else:
            raise SedParsingException('Not an append line from file command sequence')

class TestBranchCommand(SedCommand):
    COMMAND_CHAR = 't'

    def __init__(self, condition:SedCondition, branch_name:str=''):
        super().__init__(condition)
        self._branch_name = branch_name

    def _handle(self, dat:WorkingData) -> None:
        if dat.pattern_modified and self._branch_name:
            dat.jump_to = self._branch_name

    @staticmethod
    def from_string(condition:SedCondition, s:Union[str,StringParser], sandbox_mode:bool=False) -> SedCommand:
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            s.advance(1)
            s.advance_past()
            s.mark()
            s.advance_until(SOMETIMES_END_CMD_CHARS)
            branch_name = s.str_from_mark()
            return TestBranchCommand(condition, branch_name)
        else:
            raise SedParsingException('Not a test branch sequence')

class TestBranchNotCommand(SedCommand):
    COMMAND_CHAR = 'T'

    def __init__(self, condition:SedCondition, branch_name:str=''):
        super().__init__(condition)
        self._branch_name = branch_name

    def _handle(self, dat:WorkingData) -> None:
        if not dat.pattern_modified and self._branch_name:
            dat.jump_to = self._branch_name

    @staticmethod
    def from_string(condition:SedCondition, s:Union[str,StringParser], sandbox_mode:bool=False) -> SedCommand:
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            s.advance(1)
            s.advance_past()
            s.mark()
            s.advance_until(SOMETIMES_END_CMD_CHARS)
            branch_name = s.str_from_mark()
            return TestBranchNotCommand(condition, branch_name)
        else:
            raise SedParsingException('Not a test branch not sequence')

class VersionCommand(SedCommand):
    COMMAND_CHAR = 'v'

    @staticmethod
    def from_string(condition:SedCondition, s:Union[str,StringParser], sandbox_mode:bool=False) -> None:
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            s.advance(1)
            s.advance_past()
            s.mark()
            s.advance_until(SOMETIMES_END_CMD_CHARS)
            version = s.str_from_mark()

            try:
                version_parts = [int(i) for i in version.split('.', 2)]
            except ValueError:
                raise SedParsingException('Not a valid version number')

            for i,v in enumerate(version_parts):
                if v > VERSION_PARTS[i]:
                    raise SedParsingException('expected newer version of {}'.format(PACKAGE_NAME))
                elif v < VERSION_PARTS[i]:
                    break
            return None
        else:
            raise SedParsingException('Not a version sequence')

class WritePatternCommand(SedCommand):
    COMMAND_CHAR = 'w'

    def __init__(self, condition: SedCondition, file_path:str) -> None:
        super().__init__(condition)
        self._out_file = filename_to_writer(file_path)

    def _handle(self, dat:WorkingData) -> None:
        self._out_file.write(dat.pattern_space)
        self._out_file.flush()

    @staticmethod
    def from_string(condition:SedCondition, s:Union[str,StringParser], sandbox_mode:bool=False) -> SedCommand:
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            if sandbox_mode:
                raise SedParsingException('e/r/w commands disabled in sandbox mode')
            s.advance(1)
            s.advance_past()
            s.mark()
            # Semicolons are considered part of the file name string
            s.advance_end()
            return WritePatternCommand(condition, s.str_from_mark())
        else:
            raise SedParsingException('Not a write pattern command sequence')

class WritePatternToNewlineCommand(SedCommand):
    COMMAND_CHAR = 'W'

    def __init__(self, condition: SedCondition, file_path:str) -> None:
        super().__init__(condition)
        self._out_file = filename_to_writer(file_path)

    def _handle(self, dat:WorkingData) -> None:
        loc = dat.pattern_space.find(dat.newline)
        if loc < 0:
            # Shouldn't normally reach here
            self._out_file.write(dat.pattern_space)
            self._out_file.write(dat.newline)
        else:
            self._out_file.write(dat.pattern_space[:loc+1])
        self._out_file.flush()

    @staticmethod
    def from_string(condition:SedCondition, s:Union[str,StringParser], sandbox_mode:bool=False) -> SedCommand:
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            if sandbox_mode:
                raise SedParsingException('e/r/w commands disabled in sandbox mode')
            s.advance(1)
            s.advance_past()
            s.mark()
            # Semicolons are considered part of the file name string
            s.advance_end()
            return WritePatternCommand(condition, s.str_from_mark())
        else:
            raise SedParsingException('Not a write pattern command sequence')

class ExchangeCommand(SedCommand):
    COMMAND_CHAR = 'x'

    def __init__(self, condition: SedCondition) -> None:
        super().__init__(condition)

    def _handle(self, dat:WorkingData) -> None:
        temp = dat.holdspace
        dat.holdspace = dat.pattern_space
        if temp:
            dat.pattern_space = temp
        else:
            dat.pattern_space = dat.newline

    @staticmethod
    def from_string(condition:SedCondition, s:Union[str,StringParser], sandbox_mode:bool=False) -> SedCommand:
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            s.advance(1)
            s.advance_past()
            return ExchangeCommand(condition)
        else:
            raise SedParsingException('Not an exchange command sequence')

class TranslateCommand(SedCommand):
    COMMAND_CHAR = 'y'

    def __init__(self, condition: SedCondition, find_chars:str, replace_chars:str) -> None:
        super().__init__(condition)
        self.find_list = list(find_chars.encode())
        self.replace_list = list(replace_chars.encode())

    def _handle(self, dat: WorkingData) -> None:
        pattern_list = list(dat.pattern_space)
        for i in range(len(pattern_list)):
            try:
                loc = self.find_list.index(pattern_list[i])
            except ValueError:
                pass
            else:
                pattern_list[i] = self.replace_list[loc]
        dat.pattern_space = bytes(pattern_list)

    @staticmethod
    def from_string(condition:SedCondition, s:Union[str,StringParser], sandbox_mode:bool=False) -> SedCommand:
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            s.advance(1)
            find_chars, replace_chars = dual_field_command_parse(s)

            if find_chars is None or replace_chars is None:
                raise SedParsingException('unterminated `y\' command')

            if len(find_chars) != len(replace_chars):
                raise SedParsingException('strings for y command are different lengths')

            return TranslateCommand(condition, find_chars, replace_chars)
        else:
            raise SedParsingException('Not a substitute sequence')


class ZapCommand(SedCommand):
    COMMAND_CHAR = 'z'

    def __init__(self, condition:SedCondition) -> None:
        super().__init__(condition)

    def _handle(self, dat:WorkingData) -> None:
        dat.pattern_space = dat.newline

    @staticmethod
    def from_string(condition:SedCondition, s:Union[str,StringParser], sandbox_mode:bool=False) -> SedCommand:
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            s.advance(1)
            s.advance_past()
            return ZapCommand(condition)
        else:
            raise SedParsingException('Not a zap command sequence')

class CommentCommand(SedCommand):
    COMMAND_CHAR = '#'

    def __init__(self, condition:SedCondition):
        super().__init__(condition)

    @staticmethod
    def from_string(condition:SedCondition, s:Union[str,StringParser], sandbox_mode:bool=False) -> None:
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            s.advance_end()
            return None
        else:
            raise SedParsingException('Not a CommentCommand')

class PrintLineNumberCommand(SedCommand):
    COMMAND_CHAR = '='

    def __init__(self, condition:SedCondition) -> None:
        super().__init__(condition)

    def _handle(self, dat:WorkingData) -> None:
        dat.insert(str(dat.line_number).encode())

    @staticmethod
    def from_string(condition:SedCondition, s:Union[str,StringParser], sandbox_mode:bool=False) -> SedCommand:
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            s.advance(1)
            s.advance_past()
            return PrintLineNumberCommand(condition)
        else:
            raise SedParsingException('Not a print line number command sequence')

class LabelCommand(SedCommand):
    COMMAND_CHAR = ':'

    def __init__(self, condition:SedCondition, label):
        super().__init__(condition)
        self.label = label

    @staticmethod
    def from_string(condition:SedCondition, s:Union[str,StringParser], sandbox_mode:bool=False) -> SedCommand:
        if condition is not None:
            # A label cannot accept any condition
            raise SedParsingException(': doesn\'t want any addresses')

        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            s.advance(1)
            s.advance_past()
            s.mark()
            s.advance_until(SOMETIMES_END_CMD_CHARS)
            label = s.str_from_mark()
            return LabelCommand(condition, label)
        else:
            raise SedParsingException('Not a label')

SED_COMMAND_LOOKUP = {
    SubstituteCommand.COMMAND_CHAR: SubstituteCommand,
    AppendCommand.COMMAND_CHAR: AppendCommand,
    BranchCommand.COMMAND_CHAR: BranchCommand,
    ReplaceCommand.COMMAND_CHAR: ReplaceCommand,
    DeleteCommand.COMMAND_CHAR: DeleteCommand,
    DeleteToNewlineCommand.COMMAND_CHAR: DeleteToNewlineCommand,
    ExecuteCommand.COMMAND_CHAR: ExecuteCommand,
    FileCommand.COMMAND_CHAR: FileCommand,
    SetHoldspaceCommand.COMMAND_CHAR: SetHoldspaceCommand,
    AppendHoldspaceCommand.COMMAND_CHAR: AppendHoldspaceCommand,
    SetFromHoldspaceCommand.COMMAND_CHAR: SetFromHoldspaceCommand,
    AppendFromHoldspaceCommand.COMMAND_CHAR: AppendFromHoldspaceCommand,
    InsertCommand.COMMAND_CHAR: InsertCommand,
    UnambiguousPrintCommand.COMMAND_CHAR: UnambiguousPrintCommand,
    NextCommand.COMMAND_CHAR: NextCommand,
    AppendNextCommand.COMMAND_CHAR: AppendNextCommand,
    PrintCommand.COMMAND_CHAR: PrintCommand,
    PrintToNewlineCommand.COMMAND_CHAR: PrintToNewlineCommand,
    QuitCommand.COMMAND_CHAR: QuitCommand,
    QuitWithoutPrintCommand.COMMAND_CHAR: QuitWithoutPrintCommand,
    AppendFileContentsCommand.COMMAND_CHAR: AppendFileContentsCommand,
    AppendLineFromFileCommand.COMMAND_CHAR: AppendLineFromFileCommand,
    TestBranchCommand.COMMAND_CHAR: TestBranchCommand,
    TestBranchNotCommand.COMMAND_CHAR: TestBranchNotCommand,
    VersionCommand.COMMAND_CHAR: VersionCommand,
    WritePatternCommand.COMMAND_CHAR: WritePatternCommand,
    WritePatternToNewlineCommand.COMMAND_CHAR: WritePatternToNewlineCommand,
    ExchangeCommand.COMMAND_CHAR: ExchangeCommand,
    TranslateCommand.COMMAND_CHAR: TranslateCommand,
    ZapCommand.COMMAND_CHAR: ZapCommand,
    CommentCommand.COMMAND_CHAR: CommentCommand,
    PrintLineNumberCommand.COMMAND_CHAR: PrintLineNumberCommand,
    LabelCommand.COMMAND_CHAR: LabelCommand
}

class SedCommandGroup(SedCommand):
    ''' Allows a single condition to control a group of commands '''

    def __init__(self, condition:SedCondition) -> None:
        super().__init__(condition)
        self.commands:List[SedCommand] = []

    def add_commands(self, *args:Union[SedCommand, List[SedCommand]]) -> None:
        for arg in args:
            if isinstance(arg, SedCommand):
                self.commands.append(arg)
            elif isinstance(arg, list):
                self.commands.extend(arg)
            else:
                raise ValueError('Invalid type {}'.format(type(arg)))

    def clear_commands(self) -> None:
        self.commands.clear()

    def find_label(self, lbl:str) -> int:
        for i, command in enumerate(self.commands):
            if isinstance(command, SedCommandGroup):
                if command.find_label(lbl) >= 0:
                    return i
            elif command.label == lbl:
                return i
        return -1

    def get_all_labels(self) -> List[str]:
        labels = []
        for command in self.commands:
            if isinstance(command, SedCommandGroup):
                labels.extend(command.get_all_labels())
            elif command.label is not None:
                labels.append(command.label)
        return labels

    def check_labels(self) -> None:
        labels = self.get_all_labels()
        for label in labels:
            if self.find_label(label) < 0:
                raise SedParsingException(f"can't find label for jump to `{label}'")

    def _execute_label(self, dat:WorkingData, lbl:str) -> int:
        for i, command in enumerate(self.commands):
            if isinstance(command, SedCommandGroup):
                if command.jump_to_label(dat, lbl):
                    return i
            elif command.label == lbl:
                command.handle(dat)
                return i
        return -1

    def jump_to_label(self, dat:WorkingData, lbl:str) -> bool:
        index = self._execute_label(dat, lbl)
        if index < 0:
            # The label doesn't exist here
            return False
        elif dat.jump_to is not None:
            # LabelCommand found and executed. Then it jumped somewhere different
            # Let the caller handle this
            return True
        else:
            # Go right to handling label+1
            self._handle(dat, index+1)
            return True

    def _handle(self, dat: WorkingData, jump_to_idx:int=0) -> None:
        for command in self.commands[jump_to_idx:]:
            command.handle(dat)
            if dat.jump_to is not None:
                # Let the caller handle this
                return

    def _parse_expression_lines(
            self,
            script_lines:List[StringParser],
            expression_number:int,
            sandbox_mode:bool=False,
            recursion_idx:int=0
    ) -> Union[int, None]:
        for i in range(len(script_lines)):
            line = script_lines[i]
            while line.advance_past(WHITESPACE_CHARS + ';'):
                c = line[0]
                try:
                    if c in NUMBER_CHARS:
                        # Range condition
                        condition = RangeSedCondition.from_string(line)
                    elif c == '/':
                        # Regex condition
                        condition = RegexSedCondition.from_string(line)
                    else:
                        condition = None

                    if line.advance_past() and line[0] not in ';':
                        c = line[0]
                        if c == '{':
                            # Start a new group
                            line.advance(1)
                            command = SedCommandGroup(condition)
                            inc = command._parse_expression_lines(
                                script_lines[i:], expression_number, sandbox_mode, recursion_idx+1)
                            self.add_commands(command)
                            if inc is not None:
                                i += inc
                                line = script_lines[i]
                                line.advance(1)
                                continue
                            else:
                                raise SedParsingException("unmatched `{'")
                        elif c == '}':
                            if recursion_idx == 0:
                                raise SedParsingException("unexpected `}'")
                            else:
                                return i
                        else:
                            command_type = SED_COMMAND_LOOKUP.get(c, None)

                            if command_type is None:
                                raise SedParsingException(f'Invalid command: {c}')

                            command = command_type.from_string(condition, line, sandbox_mode)

                            if line.advance_past() and line[0] not in SOMETIMES_END_CMD_CHARS:
                                raise SedParsingException(f'extra characters after command')

                            if command is not None:
                                self.add_commands(command)

                    elif condition is not None:
                        raise SedParsingException('missing command')

                except SedParsingException as ex:
                    raise SedParsingException(f'Error at expression #{expression_number}, char {line.pos_offset+1}: {ex}')
            i += 1
        return None

    def add_expression(self, expression:str, expression_number:int, sandbox_mode:bool=False) -> None:
        # Since newline is always a command terminator, parse for that here
        script_lines = [StringParser(s) for s in expression.split(ALWAYS_END_CMD_CHAR)]
        # Save offset of each line for future logging
        char_offset = 0
        for line in script_lines:
            line.char_offset = char_offset
            char_offset += len(line.base_str)

        # TODO: most commands don't honor escaped newline
        # Iterate in reverse, 1 from end so that we can glue the "next" one if escaped char found
        for i in range(len(script_lines)-2, -1, -1):
            # If there are an odd number of slashes at the end of the string,
            # then next newline was escaped;
            # ex: \ escapes next \\ just means slash and \\\ means slash plus escape next
            if count_end_escapes(script_lines[i].base_str) % 2 == 1:
                # Remove escaping char, glue the next one to the end of this one, and then delete next
                script_lines[i].base_str = script_lines[i].base_str[:-1] + '\n' + script_lines[i+1].base_str
                del script_lines[i+1]

        self._parse_expression_lines(script_lines, expression_number, sandbox_mode)
