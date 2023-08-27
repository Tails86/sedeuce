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

__version__ = '0.1.1'
PACKAGE_NAME = 'sedeuce'

WHITESPACE_CHARS = (' \t\n\r\v\f\u0020\u00A0\u1680\u2000\u2001\u2002\u2003\u2004'
                    '\u2005\u2006\u2007\u2008\u2009\u200A\u202F\u205F\u3000')
NUMBER_CHARS = '0123456789'

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

class SubString:
    ''' Handles substring without modifying the original, instead keeping track of position '''
    def __init__(self, s='', start_pos=0, stop_pos=None):
        self.set(s, start_pos, stop_pos)

    def set(self, s='', start_pos=0, stop_pos=None):
        self._s = s
        self.adjust_pos(start_pos, stop_pos)

    def adjust_pos(self, start_pos=0, stop_pos=None):
        self._start_pos = start_pos
        self._stop_pos = stop_pos

    @property
    def base_str(self):
        return self._s

    @base_str.setter
    def base_str(self, s):
        self._s = s

    @property
    def slice(self):
        return slice(self.start_pos, self.stop_pos)

    @property
    def start_pos(self):
        if self._start_pos is None or self._start_pos < 0:
            return 0
        else:
            return self._start_pos

    @property
    def abs_start_pos(self):
        start_pos = self.start_pos
        if start_pos is None:
            return 0
        else:
            return start_pos

    @start_pos.setter
    def start_pos(self, pos):
        self._start_pos = pos

    @property
    def stop_pos(self):
        if self._stop_pos is not None and self._stop_pos > len(self._s):
            return len(self._s)
        else:
            return self._stop_pos

    @property
    def abs_stop_pos(self):
        stop_pos = self.stop_pos
        if stop_pos is None:
            return len(self._s)
        else:
            return stop_pos

    @stop_pos.setter
    def stop_pos(self, pos):
        self._stop_pos = pos

    def advance_start(self, inc=None):
        if inc is None:
            # Advance to end
            self._start_pos = len(self._s)
        else:
            self._start_pos += inc

    def advance_end(self, inc):
        self._stop_pos += inc

    def lstrip_self(self, characters=WHITESPACE_CHARS):
        for i in range(self.abs_start_pos, self.abs_stop_pos):
            if self._s[i] not in characters:
                self._start_pos = i
                return
        self._start_pos = len(self._s)

    def advance_start_until(self, characters=WHITESPACE_CHARS):
        for i in range(self.abs_start_pos, self.abs_stop_pos):
            if self._s[i] in characters:
                self._start_pos = i
                return
        self._start_pos = len(self._s)

    def rstrip_self(self, characters=WHITESPACE_CHARS):
        for i in range(self.abs_stop_pos - 1, self.abs_start_pos - 1, -1):
            if self._s[i] not in characters:
                self._stop_pos = i + 1
                return
        self._stop_pos = 0

    def strip_self(self, characters=WHITESPACE_CHARS):
        self.lstrip_self(characters)
        self.rstrip_self(characters)

    def __getitem__(self, val):
        offset = self.start_pos
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
        return self._s[self.slice]

    def __len__(self) -> int:
        len = self.abs_stop_pos - self.abs_start_pos
        if len < 0:
            return 0
        else:
            return len

    def startswith(self, s):
        if len(self) == 0:
            return (not s)
        else:
            return (self[0:len(s)] == s)

    def find(self, s, start=0, end=None):
        return str(self).find(s, start, end)

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

class WorkingData:
    def __init__(self) -> None:
        self.line_number = 0
        self.bytes = b''

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
    def from_string(s:SubString):
        s.lstrip_self()
        if len(s) > 0 and s[0] in NUMBER_CHARS:
            pos = s.start_pos
            s.lstrip_self(NUMBER_CHARS)
            first_num = int(s.base_str[pos:s.start_pos])
            if len(s) > 0 and s[0] == ',':
                s.advance_start(1)
                if len(s) > 0 and s[0] in NUMBER_CHARS:
                    pos = s.start_pos
                    s.lstrip_self(NUMBER_CHARS)
                    second_num = int(s.base_str[pos:s.start_pos])
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
    def from_string(s:SubString):
        s.lstrip_self()
        if len(s) > 0 and s[0] == '/':
            s.advance_start(1)
            pos = s.start_pos
            s.advance_start_until('/')
            if len(s) > 0 and s[0] == '/':
                condition = RegexSedCondition(s.base_str[pos:s.start_pos])
                s.advance_start(1)
                return condition
            else:
                raise SedParsingException('unterminated address regex')
        else:
            raise SedParsingException('Not a regex sequence')

class SedCommand:
    def __init__(self, condition:SedCondition) -> None:
        self._condition = condition

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

# Holds all currently opened files
# TODO: close files once they are no longer being used
sed_files = {}

class Substitute(SedCommand):
    COMMAND_CHAR = 's'

    def __init__(self, condition:SedCondition, find_pattern, replace_pattern):
        super().__init__(condition)
        find_pattern = _pattern_escape_invert(find_pattern, '+?|{}()')
        if isinstance(find_pattern, str):
            find_pattern = find_pattern.encode()
        self._find_bytes = find_pattern
        # TODO: implement special sequences?
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
        if self.global_replace and not self.execute_replacement:
            count = 0
        else:
            count = 1

        if self.execute_replacement:
            # This is a pain in the ass - manually go to each match in order to execute
            match_idx = 0
            offset = 0
            match = re.search(self._find, dat.bytes)
            matched = False
            while match:
                start = match.start(0) + offset
                end = match.end(0) + offset
                if self.nth_match is None or (match_idx + 1) >= self.nth_match:
                    matched = True
                    new_str = re.sub(self._find, self._replace, match.group(0))
                    # Execute the replacement
                    proc_output = subprocess.run(new_str.decode(), shell=True, capture_output=True)
                    new_dat = proc_output.stdout
                    if new_dat.endswith(b'\n'):
                        new_dat = new_dat[:-1]
                    if new_dat.endswith(b'\r'):
                        new_dat = new_dat[:-1]
                    dat.bytes = dat.bytes[0:start] + new_dat + dat.bytes[end:]
                    offset = start + len(new_dat)
                    match = re.search(self._find, dat.bytes[offset:])
                    if self.nth_match is not None and not self.global_replace:
                        # All done
                        break
                else:
                    offset = end
                    match = re.search(self._find, dat.bytes[offset:])
                match_idx += 1
            if matched:
                self._match_made(dat)
                return True
        elif self.nth_match is not None:
            for i,match in enumerate(re.finditer(self._find, dat.bytes)):
                if (i + 1) >= self.nth_match:
                    start = match.start(0)
                    dat.bytes = (
                        dat.bytes[0:start]
                        + re.sub(self._find, self._replace, dat.bytes[start:], count)
                    )
                    self._match_made(dat)
                    return True
            return False
        else:
            result = re.subn(self._find, self._replace, dat.bytes, count)
            if result[1] > 0:
                dat.bytes = result[0]
                self._match_made(dat)
                return True
            else:
                # No changes
                return False

    @staticmethod
    def from_string(condition:SedCondition, s:SubString):
        s.lstrip_self()
        if len(s) > 0 and s[0] == __class__.COMMAND_CHAR:
            splitter = s[1]
            s.advance_start(2)
            pos = s.start_pos
            s.advance_start_until(splitter)
            if len(s) == 0:
                raise SedParsingException('unterminated `s\' command')
            find_pattern = s.base_str[pos:s.start_pos]
            s.advance_start(1)
            pos = s.start_pos
            s.advance_start_until(splitter)
            if len(s) == 0:
                raise SedParsingException('unterminated `s\' command')
            replace_pattern = s.base_str[pos:s.start_pos]
            s.advance_start(1)
            command = Substitute(condition, find_pattern, replace_pattern)
            s.strip_self()
            while len(s) > 0:
                c = s[0]
                s.advance_start(1)
                if c in NUMBER_CHARS:
                    pos = s.start_pos - 1
                    s.lstrip_self(NUMBER_CHARS)
                    command.nth_match = int(s.base_str[pos:s.start_pos])
                elif c == 'g':
                    command.global_replace = True
                elif c == 'p':
                    command.print_matched_lines = True
                elif c == 'w':
                    file_name = s.base_str[s.start_pos:].strip()
                    s.advance_start() # Used the rest of the characters here
                    if file_name == '/dev/stdout':
                        command.matched_file = sys.stdout.buffer
                    elif file_name == '/dev/stderr':
                        command.matched_file = sys.stderr.buffer
                    else:
                        file_name = os.path.abspath(file_name)
                        if file_name not in sed_files:
                            sed_files[file_name] = open(file_name, 'wb')
                        command.matched_file = sed_files[file_name]
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

SED_COMMANDS = {
    Substitute.COMMAND_CHAR: Substitute
}

class Sed:
    def __init__(self):
        # TODO: support list within list when brackets are used
        self._commands = []
        self._files = []
        self.in_place = False
        self.in_place_backup_suffix = None

    def add_script(self, script:str):
        # TODO: Support brackets
        self._parse_script_lines(script.split(';'))

    def add_script_lines(self, script_lines:list):
        self._parse_script_lines(script_lines)

    def _parse_script_lines(self, script_lines):
        for i, line in enumerate(script_lines):
            substr_line = SubString(line)
            substr_line.strip_self()
            c = substr_line[0]
            condition = StaticSedCondition(True)
            try:
                if c in NUMBER_CHARS:
                    # Range condition
                    condition = RangeSedCondition.from_string(substr_line)
                elif c == '/':
                    # Regex condition
                    condition = RegexSedCondition.from_string(substr_line)
                else:
                    condition = StaticSedCondition(True)
                substr_line.lstrip_self()
                if len(substr_line) != 0:
                    command_type = SED_COMMANDS.get(substr_line[0], None)
                    if command_type is None:
                        raise SedParsingException(f'Invalid command: {substr_line[0]}')
                    command = command_type.from_string(condition, substr_line)
                    substr_line.strip_self()
                    if len(substr_line) != 0:
                        raise SedParsingException(f'unhandled: {substr_line}')
                    self._commands.append(command)
            except SedParsingException as ex:
                raise SedParsingException(f'Error at expression #{i+1}, char {substr_line.start_pos+1}: {ex}')

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
            files = [StdinIterable()]
        else:
            files = [AutoInputFileIterable(f) for f in self._files]

        line_num = 0
        for file in files:
            file_changed = False

            if self.in_place and not isinstance(file, StdinIterable):
                tmp_file = tempfile.NamedTemporaryFile(mode='wb')
                out_file = tmp_file
            else:
                tmp_file = None
                out_file = sys.stdout.buffer

            for line in file:
                line_num += 1
                dat = WorkingData()
                dat.line_number = line_num
                dat.bytes = line
                for command in self._commands:
                    if command.handle(dat):
                        file_changed = True
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
