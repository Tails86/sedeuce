#!/usr/bin/env python3

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

import os
import sys
import argparse
import re
import subprocess
import tempfile
import shutil
import threading

__version__ = '0.1.1'
PACKAGE_NAME = 'sedeuce'

# sed syntax
# \n (newline) always separates one command from the next unless proceeded by a slash: \
# ; usually separates one command from the next, but it depends on the command

# All normal whitespace chars except \n which has meaning here
WHITESPACE_CHARS = (' \t\r\v\f\u0020\u00A0\u1680\u2000\u2001\u2002\u2003\u2004'
                    '\u2005\u2006\u2007\u2008\u2009\u200A\u202F\u205F\u3000')
NUMBER_CHARS = '0123456789'
END_COMMAND_CHARS = '\n;'
REPLACE_END_COMMAND_CHARS = '\n'
APPEND_END_COMMAND_CHARS = '\n'

class SedParsingException(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)

def _pattern_escape_invert(pattern, chars):
    for char in chars:
        escaped_char = '\\' + char
        pattern_split = pattern.split(escaped_char)
        new_pattern_split = []
        for piece in pattern_split:
            new_pattern_split.append(piece.replace(char, escaped_char))
        pattern = char.join(new_pattern_split)
    return pattern

class StringParser:
    ''' Contains a string and an advancing position pointer '''

    def __init__(self, s='', pos=0):
        self.set(s, pos)
        self.mark()

    def set(self, s='', pos=0):
        self._s = s
        if pos is None or pos < 0:
            self._pos = 0
        else:
            self._pos = pos

    def mark(self):
        self._mark = self._pos

    @property
    def base_str(self):
        return self._s

    @base_str.setter
    def base_str(self, s):
        self._s = s

    @property
    def pos(self):
        if self._pos is None or self._pos < 0:
            return 0
        else:
            return self._pos

    @pos.setter
    def pos(self, pos):
        self._pos = pos

    def advance(self, inc):
        ''' Advances a set number of characters '''
        if inc is not None and inc > 0:
            self._pos += inc

    def advance_past(self, characters=WHITESPACE_CHARS):
        ''' Similar to lstrip - advances while current char is in characters
         Returns : True if pos now points to a character outside of characters
                   False if advanced to end of string '''
        for i in range(self._pos, len(self._s)):
            if self._s[i] not in characters:
                self._pos = i
                return True
        self._pos = len(self._s)
        return False

    def advance_until(self, characters=WHITESPACE_CHARS):
        ''' Advances until current char is in characters
         Returns : True if pos now points to a character within characters
                   False if advanced to end of string '''
        for i in range(self._pos, len(self._s)):
            if self._s[i] in characters:
                self._pos = i
                return True
        self._pos = len(self._s)
        return False

    def __getitem__(self, val):
        offset = self.pos
        if isinstance(val, int):
            val += offset
        elif isinstance(val, slice):
            if val.start is not None:
                val.start += offset
            if val.stop is not None:
                val.stop += offset
        else:
            raise TypeError('Invalid type for __getitem__')
        return self._s[val]

    def __str__(self) -> str:
        return self._s[self._pos:]

    def str_from(self, pos):
        ''' Returns a string from the given pos to the current pos, not including current char '''
        return self._s[pos:self._pos]

    def str_from_mark(self):
        return self.str_from(self._mark)

    def __len__(self) -> int:
        l = len(self._s) - self._pos
        if l < 0:
            return 0
        else:
            return l

    def startswith(self, s):
        if len(self) == 0:
            return (not s)
        else:
            return (self[0:len(s)] == s)

    def find(self, s, start=0, end=None):
        start += self._pos
        if end is not None:
            end += self._pos
        return self._s.find(s, start, end)

    def current_char(self):
        if len(self) <= 0:
            return ''
        else:
            return self[0]

    def is_current_char_in(self, characters):
        if len(characters) <= 0:
            raise ValueError('characters is empty')
        elif len(self) <= 0:
            # There is no current char
            return False
        else:
            return self[0] in characters

class FileIterable:
    ''' Base class for a custom file iterable '''
    # Limit each line to 128 kB which isn't human parsable at that size anyway
    LINE_BYTE_LIMIT = 128 * 1024

    def __iter__(self):
        return None

    def __next__(self):
        return None

    @property
    def name(self):
        return None

    @property
    def eof(self):
        return False

class AutoInputFileIterable(FileIterable):
    '''
    Automatically opens file on iteration and returns lines as bytes or strings.
    '''
    def __init__(self, file_path, file_mode='rb', newline_str='\n'):
        self._file_path = file_path
        self._file_mode = file_mode
        self._newline_str = newline_str
        self._as_bytes = 'b' in file_mode
        if isinstance(self._newline_str, str):
            self._newline_str = self._newline_str.encode()
        self._fp = None
        if not self._as_bytes:
            # Force reading as bytes
            self._file_mode += 'b'

    def __iter__(self):
        # Custom iteration
        self._fp = open(self._file_path, self._file_mode)
        return self

    def __next__(self):
        # Custom iteration
        if self._fp:
            b = b''
            last_b = b' '
            end = b''
            newline_len = len(self._newline_str)
            while end != self._newline_str:
                last_b = self._fp.read(1)
                if last_b:
                    if len(b) < __class__.LINE_BYTE_LIMIT:
                        b += last_b
                    # else: overflow - can be detected by checking that the line ends with newline_str
                    end += last_b
                    end = end[-newline_len:]
                else:
                    # End of file
                    self._fp = None
                    break
            if b:
                if self._as_bytes:
                    return b
                else:
                    try:
                        return b.decode()
                    except UnicodeDecodeError:
                        return b
            else:
                self._fp = None
                raise StopIteration
        else:
            raise StopIteration

    @property
    def name(self):
        return self._file_path

    @property
    def eof(self):
        return (self._fp is None)

class StdinIterable(FileIterable):
    '''
    Reads from stdin and returns lines as bytes or strings.
    '''
    def __init__(self, as_bytes=True, end='\n', label='(standard input)'):
        self._as_bytes = as_bytes
        self._end = end
        self._label = label
        if isinstance(self._end, str):
            self._end = self._end.encode()
        self._eof_detected = False

    def __iter__(self):
        # Custom iteration
        self._eof_detected = False
        return self

    def __next__(self):
        # Custom iteration
        if self._eof_detected:
            raise StopIteration
        b = b''
        end = b''
        end_len = len(self._end)
        while end != self._end:
            last_b = sys.stdin.buffer.read(1)
            if last_b:
                if len(b) < __class__.LINE_BYTE_LIMIT:
                    b += last_b
                # else: overflow - can be detected by checking that the line ends with end
                end += last_b
                end = end[-end_len:]
            else:
                self._eof_detected = True
                break
        if self._as_bytes:
            return b
        else:
            try:
                return b.decode()
            except UnicodeDecodeError:
                return b

    @property
    def name(self):
        return self._label

    @property
    def eof(self):
        return self._eof_detected

class SharedFileWriter:
    ''' Simple file writer used when multiple objects need to write to the same file '''
    files = {}
    files_mutex = threading.Semaphore(1)

    def __init__(self, file_path, binary=True, append=False):
        file_path = os.path.abspath(file_path)
        self._file_path = file_path
        with __class__.files_mutex:
            if file_path not in __class__.files:
                if append:
                    mode = 'a'
                else:
                    mode = 'w'

                if binary:
                    mode += 'b'

                __class__.files[file_path] = {
                    'file': open(file_path, mode),
                    'count': 0
                }
            self._file_entry = __class__.files[file_path]
            self._file_entry['count'] += 1
            self._file = self._file_entry['file']
        # Copy over write and flush methods
        self.write = self._file.write
        self.flush = self._file.flush

    def __del__(self):
        with __class__.files_mutex:
            __class__.files[self._file_path]['count'] -= 1
            if __class__.files[self._file_path]['count'] <= 0:
                # File is no longer used
                del __class__.files[self._file_path]
                self._file.close()

class WorkingData:
    def __init__(self) -> None:
        self.newline = b'\n'
        self.line_number = 0
        self.bytes = b''
        self.jump_to = None

class SedCondition:
    def is_match(self, dat:WorkingData) -> bool:
        return False

class StaticSedCondition(SedCondition):
    def __init__(self, static_value) -> None:
        super().__init__()
        self._static_value = static_value

    def is_match(self, dat:WorkingData) -> bool:
        return self._static_value

class RangeSedCondition(SedCondition):
    def __init__(self, start_line, end_line = None) -> None:
        super().__init__()
        self._start_line = start_line
        if end_line is not None:
            self._end_line = end_line
        else:
            self._end_line = start_line

    def is_match(self, dat: WorkingData) -> bool:
        return dat.line_number >= self._start_line and dat.line_number <= self._end_line

    @staticmethod
    def from_string(s:StringParser):
        if s.advance_past() and s[0] in NUMBER_CHARS:
            s.mark()
            s.advance_past(NUMBER_CHARS)
            first_num = int(s.str_from_mark())
            if len(s) > 0 and s[0] == ',':
                s.advance(1)
                if len(s) > 0 and s[0] in NUMBER_CHARS:
                    s.mark()
                    s.advance_past(NUMBER_CHARS)
                    second_num = int(s.str_from_mark())
                    return RangeSedCondition(first_num, second_num)
                else:
                    raise SedParsingException('unexpected `,\'')
            else:
                return RangeSedCondition(first_num)
        else:
            raise SedParsingException('Not a range sequence')


class RegexSedCondition(SedCondition):
    def __init__(self, pattern) -> None:
        super().__init__()
        self._pattern = _pattern_escape_invert(pattern, '+?|{}()')
        if isinstance(self._pattern, str):
            self._pattern = self._pattern.encode()

    def is_match(self, dat: WorkingData) -> bool:
        return (re.match(self._pattern, dat.bytes) is not None)

    @staticmethod
    def from_string(s:StringParser):
        if s.advance_past() and s[0] == '/':
            s.advance(1)
            s.mark()
            if s.advance_until('/'):
                condition = RegexSedCondition(s.str_from_mark())
                s.advance(1)
                return condition
            else:
                raise SedParsingException('unterminated address regex')
        else:
            raise SedParsingException('Not a regex sequence')

class SedCommand:
    def __init__(self, condition:SedCondition) -> None:
        self._condition = condition
        self.label = None

    def handle(self, dat:WorkingData) -> bool:
        if self._condition is None or self._condition.is_match(dat):
            return self._handle(dat)
        else:
            return False

    @staticmethod
    def _print_bytes(b:bytes):
        sys.stdout.buffer.write(b)
        sys.stdout.buffer.flush()

    def _handle(self, dat:WorkingData) -> bool:
        return False

class SubstituteCommand(SedCommand):
    COMMAND_CHAR = 's'

    def __init__(self, condition:SedCondition, find_pattern, replace_pattern):
        super().__init__(condition)
        find_pattern = _pattern_escape_invert(find_pattern, '+?|{}()')
        if isinstance(find_pattern, str):
            find_pattern = find_pattern.encode()
        self._find_bytes = find_pattern
        self._only_first_match = self._find_bytes.startswith(b'^')
        # TODO: implement special sequences using replace callback instead?
        self._replace = replace_pattern
        if isinstance(self._replace, str):
            self._replace = self._replace.encode()

        self.global_replace = False
        self.nth_match = None
        self.print_matched_lines = False
        self.matched_file = None
        self.execute_replacement = False
        self._ignore_case = False
        # This gives a bit different implementation within re
        self._multiline_mode = False

        self._compile_find()

    @property
    def ignore_case(self):
        return self._ignore_case

    @ignore_case.setter
    def ignore_case(self, ignore_case):
        if self._ignore_case != ignore_case:
            self._ignore_case = ignore_case
            # Need to recompile find
            self._compile_find()

    @property
    def multiline_mode(self):
        return self._multiline_mode

    @multiline_mode.setter
    def multiline_mode(self, multiline_mode):
        if self._multiline_mode != multiline_mode:
            self._multiline_mode = multiline_mode
            # Need to recompile find
            self._compile_find()

    def _compile_find(self):
        flags = 0
        if self._ignore_case:
            flags |= re.IGNORECASE
        self._find = re.compile(self._find_bytes, flags)

    def _match_made(self, dat:WorkingData):
        if self.print_matched_lines:
            self._print_bytes(dat.bytes)
        if self.matched_file is not None:
            self.matched_file.write(dat.bytes)
            self.matched_file.flush()

    def _handle(self, dat:WorkingData) -> bool:
        # Determine what nth match is based on self data
        nth_match = self.nth_match
        if self._only_first_match:
            if self.nth_match is not None:
                if (self.nth_match == 0 and not self.global_replace) or self.nth_match > 1:
                    # No way to ever match this
                    return False
                else:
                    # Only first match is valid
                    nth_match = 1

        if nth_match is None and not self.global_replace:
            nth_match = 1

        # This is a pain in the ass - manually go to each match in order to handle all features
        match_idx = 0
        offset = 0
        next_chunk = dat.bytes
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
                    proc_output = subprocess.run(new_str.decode(), shell=True, capture_output=True)
                    new_dat = proc_output.stdout
                    if new_dat.endswith(b'\n'):
                        new_dat = new_dat[:-1]
                    if new_dat.endswith(b'\r'):
                        new_dat = new_dat[:-1]
                else:
                    new_dat = new_str
                dat.bytes = dat.bytes[0:start] + new_dat + dat.bytes[end:]
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
            next_chunk = dat.bytes[offset:]
            match = re.search(self._find, next_chunk)
            match_idx += 1
        if matched:
            self._match_made(dat)
            return True

    @staticmethod
    def from_string(condition:SedCondition, s):
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            splitter = s[1]
            s.advance(2)
            s.mark()
            if not s.advance_until(splitter):
                raise SedParsingException('unterminated `s\' command')
            find_pattern = s.str_from_mark()
            s.advance(1)
            s.mark()
            if not s.advance_until(splitter):
                raise SedParsingException('unterminated `s\' command')
            replace_pattern = s.str_from_mark()
            s.advance(1)
            command = SubstituteCommand(condition, find_pattern, replace_pattern)
            while s.advance_past() and s[0] not in END_COMMAND_CHARS:
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
                    s.mark()
                    s.advance_until(END_COMMAND_CHARS) # Used the rest of the characters here
                    file_name = s.str_from_mark().strip()
                    if file_name == '/dev/stdout':
                        command.matched_file = sys.stdout.buffer
                    elif file_name == '/dev/stderr':
                        command.matched_file = sys.stderr.buffer
                    else:
                        command.matched_file = SharedFileWriter(file_name, binary=True, append=False)
                elif c == 'e':
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

    def __init__(self, condition: SedCondition, append_value):
        super().__init__(condition)
        if isinstance(append_value, str):
            self._append_value = append_value.encode()
        else:
            self._append_value = append_value

    def _handle(self, dat:WorkingData) -> bool:
        if not dat.bytes.endswith(dat.newline):
            dat.bytes += dat.newline
        dat.bytes += self._append_value + dat.newline

    @staticmethod
    def from_string(condition:SedCondition, s):
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            s.advance(1)
            if len(s) > 0 and s[0] == '\\':
                s.advance(1)
            else:
                s.advance_past()
            s.mark()
            s.advance_until(APPEND_END_COMMAND_CHARS)
            return AppendCommand(condition, s.str_from_mark())
        else:
            raise SedParsingException('Not an append sequence')

class BranchCommand(SedCommand):
    COMMAND_CHAR = 'b'

    def __init__(self, condition: SedCondition, branch_name=''):
        super().__init__(condition)
        self._branch_name = branch_name

    def _handle(self, dat:WorkingData) -> bool:
        if self._branch_name:
            dat.jump_to = self._branch_name
        return False

    @staticmethod
    def from_string(condition:SedCondition, s):
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            s.advance(1)
            s.advance_past()
            s.mark()
            s.advance_until(END_COMMAND_CHARS)
            branch_name = s.str_from_mark()
            return BranchCommand(condition, branch_name)
        else:
            raise SedParsingException('Not a branch sequence')

class ReplaceCommand(SedCommand):
    COMMAND_CHAR = 'c'

    def __init__(self, condition: SedCondition, replace):
        super().__init__(condition)
        if isinstance(replace, str):
            self._replace = replace.encode()
        else:
            self._replace = replace

    def _handle(self, dat:WorkingData) -> bool:
        add_newline = dat.bytes.endswith(dat.newline)
        dat.bytes = self._replace
        if add_newline:
            dat.bytes += dat.newline
        return True

    @staticmethod
    def from_string(condition:SedCondition, s):
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            s.advance(1)
            if len(s) > 0 and s[0] == '\\':
                s.advance(1)
            else:
                s.advance_past()
            s.mark()
            s.advance_until(REPLACE_END_COMMAND_CHARS)
            replace = s.str_from_mark()
            return ReplaceCommand(condition, replace)
        else:
            raise SedParsingException('Not a replace sequence')

class DeleteToNewlineCommand(SedCommand):
    # There doesn't seem to be a difference between these two
    COMMAND_CHAR = 'd'
    COMMAND_CHAR2 = 'D'

    def __init__(self, condition: SedCondition):
        super().__init__(condition)

    def _handle(self, dat:WorkingData) -> bool:
        pos = dat.bytes.find(dat.newline)
        if pos >= 0:
            dat.bytes = dat.bytes[pos+1:]
        else:
            dat.bytes = b''
        dat.jump_to = -1 # jump to end
        self._last_processed_line = dat.line_number
        return True

    @staticmethod
    def from_string(condition:SedCondition, s):
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            s.advance(1)
            s.advance_past()
            return DeleteToNewlineCommand(condition)
        else:
            raise SedParsingException('Not a delete command')

class Label(SedCommand):
    COMMAND_CHAR = ':'

    def __init__(self, condition: SedCondition, label):
        super().__init__(condition)
        self.label = label

    @staticmethod
    def from_string(condition:SedCondition, s):
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            s.advance(1)
            s.advance_past()
            s.mark()
            s.advance_until(END_COMMAND_CHARS)
            label = s.str_from_mark()
            return Label(condition, label)
        else:
            raise SedParsingException('Not a label')

SED_COMMANDS = {
    SubstituteCommand.COMMAND_CHAR: SubstituteCommand,
    AppendCommand.COMMAND_CHAR: AppendCommand,
    BranchCommand.COMMAND_CHAR: BranchCommand,
    ReplaceCommand.COMMAND_CHAR: ReplaceCommand,
    DeleteToNewlineCommand.COMMAND_CHAR: DeleteToNewlineCommand,
    DeleteToNewlineCommand.COMMAND_CHAR2: DeleteToNewlineCommand,
    Label.COMMAND_CHAR: Label
}

class Sed:
    def __init__(self):
        self._commands = []
        self._files = []
        self.in_place = False
        self.in_place_backup_suffix = None
        self.newline = '\n'

    @property
    def newline(self):
        return self._newline

    @newline.setter
    def newline(self, newline):
        if isinstance(newline, str):
            self._newline = newline.encode()
        else:
            self._newline = newline

    def add_script(self, script:str):
        # TODO: Support brackets
        # Since newline is always a command terminator, parse for that here
        script_lines = script.split('\n')
        # Iterate in reverse, 1 from end so that we can glue the "next" one if escaped char found
        for i in range(len(script_lines)-2, -1, -1):
            # If there are an odd number of slashes at the end of the string,
            # then next newline was escaped;
            # ex: \ escapes next \\ just means slash and \\\ means slash plus escape next
            count = 0
            for c in reversed(script_lines[i]):
                if c == '\\':
                    count += 1
                else:
                    break
            if count % 2 == 1:
                # Glue the next one to the end of this one then delete next
                script_lines[i] += script_lines[i+1]
                del script_lines[i+1]

        self._parse_script_lines(script_lines)

    def add_script_lines(self, script_lines:list):
        self._parse_script_lines(script_lines)

    def _parse_script_lines(self, script_lines):
        for i, line in enumerate(script_lines):
            substr_line = StringParser(line)
            while len(substr_line) > 0:
                substr_line.advance_past()
                c = substr_line[0]
                try:
                    if c in NUMBER_CHARS:
                        # Range condition
                        condition = RangeSedCondition.from_string(substr_line)
                    elif c == '/':
                        # Regex condition
                        condition = RegexSedCondition.from_string(substr_line)
                    else:
                        condition = None
                    if substr_line.advance_past() and substr_line[0] not in END_COMMAND_CHARS:
                        command_type = SED_COMMANDS.get(substr_line[0], None)
                        if command_type is None:
                            raise SedParsingException(f'Invalid command: {substr_line[0]}')
                        command = command_type.from_string(condition, substr_line)
                        if substr_line.advance_past() and substr_line[0] not in END_COMMAND_CHARS:
                            raise SedParsingException(f'extra characters after command')
                        substr_line.advance_past(WHITESPACE_CHARS + END_COMMAND_CHARS)
                        self._commands.append(command)
                    elif condition is not None:
                        raise SedParsingException('missing command')
                except SedParsingException as ex:
                    raise SedParsingException(f'Error at expression #{i+1}, char {substr_line.pos+1}: {ex}')

    def add_command(self, command_or_commands):
        if isinstance(command_or_commands, list):
            self._commands.extend(command_or_commands)
        else:
            self._commands.append(command_or_commands)

    def clear_commands(self):
        self._commands.clear()

    def add_file(self, file_or_files):
        if isinstance(file_or_files, list):
            self._files.extend(file_or_files)
        else:
            self._files.append(file_or_files)

    def clear_files(self):
        self._files.clear()

    def execute(self):
        if not self._files:
            files = [StdinIterable(end=self.newline)]
        else:
            files = [AutoInputFileIterable(f, newline_str=self.newline) for f in self._files]

        line_num = 0
        for file in files:
            file_changed = False

            if self.in_place and not isinstance(file, StdinIterable):
                # Write to temporary file to be copied to target when it changes
                tmp_file = tempfile.NamedTemporaryFile(mode='wb')
                out_file = tmp_file
            else:
                tmp_file = None
                out_file = sys.stdout.buffer

            for line in file:
                line_num += 1
                dat = WorkingData()
                dat.newline = self.newline
                dat.line_number = line_num
                dat.bytes = line
                i = 0
                while i < len(self._commands):
                    command = self._commands[i]
                    i += 1
                    if command.handle(dat):
                        file_changed = True
                    # Command may set jump_to when we need to jump to another command
                    if dat.jump_to is not None:
                        jump_to = dat.jump_to
                        dat.jump_to = None
                        # jump_to may be an index or label
                        if isinstance(jump_to, int):
                            if jump_to < 0:
                                # Jump to end
                                i = len(self._commands)
                            else:
                                # Jump to index (usually 0)
                                i = jump_to
                        else:
                            i = -1
                            for j,c in enumerate(self._commands):
                                if c.label == jump_to:
                                    i = j
                                    break
                            if i < 0:
                                raise SedParsingException(f"can't find label for jump to `{jump_to}'")
                # Write the line to destination
                out_file.write(dat.bytes)
                out_file.flush()

            if file_changed and tmp_file:
                # Write data from temp file to destination
                tmp_file.flush()
                file_name = os.path.abspath(file.name)
                if self.in_place_backup_suffix is not None:
                    backup_name = file_name + self.in_place_backup_suffix
                    shutil.copy2(file_name, backup_name)
                os.remove(file_name)
                shutil.copy2(tmp_file.name, file_name)
                del tmp_file

def parse_args(cliargs):
    parser = argparse.ArgumentParser(
        prog=PACKAGE_NAME,
        description='A sed clone in Python with both CLI and library interfaces',
        epilog='NOTE: Only substitute command is currently available'
    )

    parser.add_argument('script', type=str, nargs='?',
                        help='script, only if no other script defined below')
    parser.add_argument('input_file', metavar='input-file', type=str, nargs='*', default=[],
                        help='Input file(s) to parse')

    # parser.add_argument('-n', '--quiet', '--silent', action='store_true',
    #                     help='suppress automatic printing of pattern space')
    # parser.add_argument('--debug', action='store_true', help='annotate program execution')
    # parser.add_argument('-e', '--expression', metavar='script', type=str, default=None,
    #                     help='add the contents of script-file to the commands to be executed')
    # parser.add_argument('-f', '--file', metavar='script-file', type=str, default=None,
    #                     help='add the contents of script-file to the commands to be executed')
    # parser.add_argument('--follow-symlinks', action='store_true',
    #                     help='follow symlinks when processing in place')
    parser.add_argument('-i', '--in-place', metavar='SUFFIX', nargs='?', type=str, default=None,
                        const=True,
                        help='edit files in place (makes backup if SUFFIX supplied)')
    # parser.add_argument('-l', '--line-length', metavar='N', type=int, default=None,
    #                     help='specify the desired line-wrap length for the `l\' command')
    # parser.add_argument('--posix', action='store_true', help='disable all GNU extensions.')
    # parser.add_argument('-E', '-r', '--regexp-extended', action='store_true',
    #                     help='use extended regular expressions in the script')
    # parser.add_argument('-s', '--separate', action='store_true',
    #                     help='consider files as separate rather than as a single, '
    #                     'continuous long stream.')
    # parser.add_argument('--sandbox', action='store_true',
    #                     help='operate in sandbox mode (disable e/r/w commands).')
    # parser.add_argument('-u', '--unbuffered', action='store_true',
    #                     help='load minimal amounts of data from the input files and flush '
    #                     'the output buffers more often')
    # parser.add_argument('-z', '--null-data', action='store_true',
    #                     help='separate lines by NUL characters')
    parser.add_argument('--version', action='store_true',
                        help='output version information and exit')
    parser.add_argument('--verbose', action='store_true', help='show verbose errors')
    args = parser.parse_args(cliargs)
    return args

def main(cliargs):
    args = parse_args(cliargs)
    if args.version:
        print('{} {}'.format(PACKAGE_NAME, __version__))
        return 0
    if not args.script:
        print('No script provided')
        return 1
    sed = Sed()
    try:
        sed.add_script(args.script)
        if args.input_file:
            sed.add_file(args.input_file)
        if args.in_place is not None:
            sed.in_place = True
            if isinstance(args.in_place, str):
                sed.in_place_backup_suffix = args.in_place
        sed.execute()
    except Exception as ex:
        if args.verbose:
            raise ex
        else:
            print(f'{PACKAGE_NAME}: {ex}', file=sys.stderr)
