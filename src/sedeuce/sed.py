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

VERSION_PARTS = [int(i) for i in __version__.split('.')]

# sed syntax
# \n (newline) always separates one command from the next unless proceeded by a slash: \
# ; usually separates one command from the next, but it depends on the command

WHITESPACE_CHARS = (' \t\r\n\v\f\u0020\u00A0\u1680\u2000\u2001\u2002\u2003\u2004'
                    '\u2005\u2006\u2007\u2008\u2009\u200A\u202F\u205F\u3000')
NUMBER_CHARS = '0123456789'
SOMETIMES_END_CMD_CHAR = ';'
ALWAYS_END_CMD_CHAR = '\n'

class SedParsingException(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)

class SedQuitException(Exception):
    def __init__(self, exit_code:int) -> None:
        super().__init__()
        self.exit_code = exit_code

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

    def advance_end(self):
        ''' Advance pointer to end of string '''
        self._pos = len(self._s)

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

    def __del__(self):
        if self._fp:
            self._fp.close()
            self._fp = None

    def __iter__(self):
        # Custom iteration
        if self._fp:
            self._fp.close()
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
                    self._fp.close()
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

def _filename_to_writer(file_name):
    if file_name == '/dev/stdout':
        return sys.stdout.buffer
    elif file_name == '/dev/stderr':
        return sys.stderr.buffer
    else:
        return SharedFileWriter(file_name, binary=True, append=False)

class WorkingData:
    def __init__(self) -> None:
        self.newline = b'\n'
        self.in_file = None
        self.in_file_iter = None
        self.out_file = sys.stdout.buffer
        self.line_number = 0
        self.pattern_modified = False
        self.file_modified = False
        self.insert_space = None
        self._pattern_space = None
        self.append_space = None
        self.jump_to = None
        self.holdspace = b''

    def set_in_file(self, file:FileIterable):
        self.file_modified = False
        self.in_file = file
        # This will raise an exception if file could not be opened
        self.in_file_iter = iter(self.in_file)

    @property
    def file_name(self):
        return self.in_file.name

    def next_line(self) -> bool:
        self.flush_all_data()

        if not self.in_file_iter:
            return False

        try:
            self._pattern_space = next(self.in_file_iter)
            self.pattern_modified = False
        except StopIteration:
            self.in_file_iter = None
            return False
        else:
            self.line_number += 1
            return True

    def append_next_line(self) -> bool:
        if not self.in_file_iter:
            self.flush_all_data()
            return False

        try:
            append_pattern = next(self.in_file_iter)
        except StopIteration:
            self.flush_all_data()
            self.in_file_iter = None
            return False
        else:
            # Flush out insert and append data then append the pattern space
            self._flush_insert_data()
            self._flush_append_data()
            if self._pattern_space and not self._pattern_space.endswith(self.newline):
                self._pattern_space += self.newline
            self._pattern_space += append_pattern
            self.line_number += 1
            return True

    def insert(self, i:bytes, add_newline=True):
        # Append to insert space
        if self.insert_space is None:
            self.insert_space = i
        else:
            self.insert_space += i

        if add_newline and not self.insert_space.endswith(self.newline):
            self.insert_space += self.newline

        self.file_modified = True

    @property
    def pattern_space(self):
        return self._pattern_space

    @pattern_space.setter
    def pattern_space(self, b:bytes):
        self._pattern_space = b
        self.file_modified = True
        self.pattern_modified = True

    def append(self, a:bytes, add_newline=True):
        # Append to append space
        if self.append_space is None:
            self.append_space = a
        else:
            self.append_space += a

        if add_newline and not self.append_space.endswith(self.newline):
            self.append_space += self.newline

        self.file_modified = True

    def _write(self, b:bytes):
        self.out_file.write(b)
        self.out_file.flush()

    def _flush_insert_data(self):
        if self.insert_space is not None:
            self.file_modified = True
            self._write(self.insert_space)
            self.insert_space = None

    def _flush_append_data(self):
        if self.append_space is not None:
            self.file_modified = True
            if self.pattern_space and not self.pattern_space.endswith(self.newline):
                self._write(self.newline)
            self._write(self.append_space)
            self.append_space = None

    def print_bytes(self, b:bytes):
        self._write(b)
        self.file_modified = True

    def flush_all_data(self):
        self._flush_insert_data()

        if self._pattern_space is not None:
            # Write the modified pattern space
            self._write(self.pattern_space)
            self._pattern_space = None
            self.pattern_modified = False

        self._flush_append_data()

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

    def is_match(self, dat:WorkingData) -> bool:
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

    def is_match(self, dat:WorkingData) -> bool:
        return (re.match(self._pattern, dat.pattern_space) is not None)

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

    def handle(self, dat:WorkingData) -> None:
        if self._condition is None or self._condition.is_match(dat):
            self._handle(dat)

    def _handle(self, dat:WorkingData) -> None:
        pass

class SubstituteCommand(SedCommand):
    COMMAND_CHAR = 's'

    def __init__(self, condition:SedCondition, find_pattern, replace_pattern):
        super().__init__(condition)
        find_pattern = _pattern_escape_invert(find_pattern, '+?|{}()')
        if isinstance(find_pattern, str):
            find_pattern = find_pattern.encode()
        # TODO: The $ character should correspond to newline character
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
            dat.print_bytes(dat.pattern_space)
        if self.matched_file is not None:
            self.matched_file.write(dat.pattern_space)
            self.matched_file.flush()

    def _handle(self, dat:WorkingData) -> None:
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
                    proc_output = subprocess.run(new_str.decode(), shell=True, capture_output=True)
                    new_dat = proc_output.stdout
                    if new_dat.endswith(b'\n'):
                        new_dat = new_dat[:-1]
                    if new_dat.endswith(b'\r'):
                        new_dat = new_dat[:-1]
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
            while s.advance_past() and s[0] not in SOMETIMES_END_CMD_CHAR:
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
                    s.advance_until(SOMETIMES_END_CMD_CHAR) # Used the rest of the characters here
                    file_name = s.str_from_mark().strip()
                    command.matched_file = _filename_to_writer(file_name)
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

    def _handle(self, dat:WorkingData) -> None:
        dat.append(self._append_value)

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
            # Semicolons are considered part of the append string
            s.advance_end()
            return AppendCommand(condition, s.str_from_mark())
        else:
            raise SedParsingException('Not an append sequence')

class BranchCommand(SedCommand):
    COMMAND_CHAR = 'b'

    def __init__(self, condition: SedCondition, branch_name=''):
        super().__init__(condition)
        self._branch_name = branch_name

    def _handle(self, dat:WorkingData) -> None:
        if self._branch_name:
            dat.jump_to = self._branch_name
        return

    @staticmethod
    def from_string(condition:SedCondition, s):
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            s.advance(1)
            s.advance_past()
            s.mark()
            s.advance_until(SOMETIMES_END_CMD_CHAR)
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

    def _handle(self, dat:WorkingData) -> None:
        add_newline = dat.pattern_space.endswith(dat.newline)
        dat.pattern_space = self._replace
        if add_newline:
            dat.pattern_space += dat.newline
        return

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
            # Semicolons are considered part of the replace string
            s.advance_end()
            replace = s.str_from_mark()
            return ReplaceCommand(condition, replace)
        else:
            raise SedParsingException('Not a replace sequence')

class DeleteCommand(SedCommand):
    COMMAND_CHAR = 'd'

    def __init__(self, condition: SedCondition):
        super().__init__(condition)

    def _handle(self, dat:WorkingData) -> None:
        dat.pattern_space = b''
        dat.jump_to = -1 # jump to end

    @staticmethod
    def from_string(condition:SedCondition, s):
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

    def __init__(self, condition: SedCondition):
        super().__init__(condition)

    def _handle(self, dat:WorkingData) -> None:
        pos = dat.pattern_space.find(dat.newline)
        if pos >= 0:
            dat.pattern_space = dat.pattern_space[pos+1:]
            dat.jump_to = 0 # jump to beginning
        else:
            dat.pattern_space = b''
            dat.jump_to = -1 # jump to end
        self._last_processed_line = dat.line_number
        return

    @staticmethod
    def from_string(condition:SedCondition, s):
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
            proc_output = subprocess.run(self.cmd, shell=True, capture_output=True)
            dat.pattern_space = proc_output.stdout + dat.pattern_space
        else:
            # Execute what's in the pattern space and replace the pattern space with the output
            proc_output = subprocess.run(dat.pattern_space.decode(), shell=True, capture_output=True)
            dat.pattern_space = proc_output.stdout
        return

    @staticmethod
    def from_string(condition:SedCondition, s):
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
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

    def __init__(self, condition: SedCondition) -> None:
        super().__init__(condition)

    def _handle(self, dat:WorkingData) -> None:
        dat.print_bytes(dat.file_name.encode() + dat.newline)
        return

    @staticmethod
    def from_string(condition:SedCondition, s):
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            s.advance(1)
            s.advance_past()
            return FileCommand(condition)
        else:
            raise SedParsingException('Not a file sequence')

class SetHoldspace(SedCommand):
    COMMAND_CHAR = 'h'

    def __init__(self, condition: SedCondition) -> None:
        super().__init__(condition)

    def _handle(self, dat:WorkingData) -> None:
        dat.holdspace = dat.pattern_space
        return

    @staticmethod
    def from_string(condition:SedCondition, s):
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            s.advance(1)
            s.advance_past()
            return SetHoldspace(condition)
        else:
            raise SedParsingException('Not a set holdspace sequence')

class AppendHoldspace(SedCommand):
    COMMAND_CHAR = 'H'

    def __init__(self, condition: SedCondition) -> None:
        super().__init__(condition)

    def _handle(self, dat:WorkingData) -> None:
        holdspace = dat.holdspace
        if not holdspace.endswith(dat.newline):
            holdspace += dat.newline
        dat.holdspace = holdspace + dat.pattern_space
        return

    @staticmethod
    def from_string(condition:SedCondition, s):
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            s.advance(1)
            s.advance_past()
            return AppendHoldspace(condition)
        else:
            raise SedParsingException('Not an append holdspace sequence')

class SetFromHoldspace(SedCommand):
    COMMAND_CHAR = 'g'

    def __init__(self, condition: SedCondition) -> None:
        super().__init__(condition)

    def _handle(self, dat:WorkingData) -> None:
        holdspace = dat.holdspace
        if not holdspace.endswith(dat.newline):
            holdspace += dat.newline
        dat.pattern_space = holdspace
        return

    @staticmethod
    def from_string(condition:SedCondition, s):
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            s.advance(1)
            s.advance_past()
            return SetFromHoldspace(condition)
        else:
            raise SedParsingException('Not a set from holdspace sequence')

class AppendFromHoldspace(SedCommand):
    COMMAND_CHAR = 'G'

    def __init__(self, condition: SedCondition) -> None:
        super().__init__(condition)

    def _handle(self, dat:WorkingData) -> None:
        dat.append(dat.holdspace)

    @staticmethod
    def from_string(condition:SedCondition, s):
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            s.advance(1)
            s.advance_past()
            return AppendFromHoldspace(condition)
        else:
            raise SedParsingException('Not an append from holdspace sequence')

class InsertCommand(SedCommand):
    COMMAND_CHAR = 'i'

    def __init__(self, condition: SedCondition, insert_value):
        super().__init__(condition)
        if isinstance(insert_value, str):
            self._insert_value = insert_value.encode()
        else:
            self._insert_value = insert_value

    def _handle(self, dat:WorkingData) -> None:
        dat.insert(self._insert_value)
        return

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
            # Semicolons are considered part of the append string
            s.advance_end()
            return InsertCommand(condition, s.str_from_mark())
        else:
            raise SedParsingException('Not an insert sequence')

class UnambiguousPrint(SedCommand):
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

    def __init__(self, condition: SedCondition) -> None:
        super().__init__(condition)

    @staticmethod
    def _convert_byte(b:int, newline_char:bytes):
        if b == ord(newline_char):
            return [ord('$'), b]
        elif b in __class__.CONVERSION_DICT:
            return __class__.CONVERSION_DICT[b]
        elif b < 32 or b > 126:
            return list(b'\\' + '{:o}'.format(b).encode())
        else:
            return [b]

    def _handle(self, dat:WorkingData) -> None:
        the_bytes = bytes([b for a in dat.pattern_space for b in __class__._convert_byte(a, dat.newline)])
        # Need to add $ if the current line does not end with newline
        if not dat.pattern_space.endswith(dat.newline):
            the_bytes += b'$'
        dat.print_bytes(the_bytes)

    @staticmethod
    def from_string(condition:SedCondition, s):
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            s.advance(1)
            s.advance_past()
            return UnambiguousPrint(condition)
        else:
            raise SedParsingException('Not an unambiguous print sequence')

class NextCommand(SedCommand):
    COMMAND_CHAR = 'n'

    def __init__(self, condition: SedCondition) -> None:
        super().__init__(condition)

    def _handle(self, dat:WorkingData) -> None:
        dat.next_line()

    @staticmethod
    def from_string(condition:SedCondition, s):
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

    def __init__(self, condition: SedCondition) -> None:
        super().__init__(condition)

    def _handle(self, dat:WorkingData) -> None:
        dat.append_next_line()

    @staticmethod
    def from_string(condition:SedCondition, s):
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

    def __init__(self, condition: SedCondition) -> None:
        super().__init__(condition)

    def _handle(self, dat:WorkingData) -> None:
        dat.print_bytes(dat.pattern_space)

    @staticmethod
    def from_string(condition:SedCondition, s):
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

    def __init__(self, condition: SedCondition) -> None:
        super().__init__(condition)

    def _handle(self, dat:WorkingData) -> None:
        loc = dat.pattern_space.find(dat.newline)
        if loc < 0:
            dat.print_bytes(dat.pattern_space + dat.newline)
        else:
            dat.print_bytes(dat.pattern_space[:loc+1])

    @staticmethod
    def from_string(condition:SedCondition, s):
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

    def __init__(self, condition: SedCondition, exit_code=0) -> None:
        super().__init__(condition)
        self.exit_code = exit_code

    def _handle(self, dat:WorkingData) -> None:
        dat.flush_all_data()
        raise SedQuitException(self.exit_code)

    @staticmethod
    def from_string(condition:SedCondition, s):
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

    def __init__(self, condition: SedCondition, exit_code=0) -> None:
        super().__init__(condition)
        self.exit_code = exit_code

    def _handle(self, dat:WorkingData) -> None:
        dat._flush_insert_data() # Only flush insert data before quitting
        raise SedQuitException(self.exit_code)

    @staticmethod
    def from_string(condition:SedCondition, s):
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

class AppendFileContents(SedCommand):
    COMMAND_CHAR = 'r'

    def __init__(self, condition: SedCondition, file_path) -> None:
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
    def from_string(condition:SedCondition, s):
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            s.advance(1)
            s.advance_past()
            s.mark()
            # Semicolons are considered part of the file name string
            s.advance_end()
            return AppendFileContents(condition, s.str_from_mark())
        else:
            raise SedParsingException('Not an append file contents command sequence')

class AppendLineFromFile(SedCommand):
    COMMAND_CHAR = 'R'

    def __init__(self, condition: SedCondition, file_path) -> None:
        super().__init__(condition)
        self.file_path = file_path
        self.file_read = False
        self.file_iter = None

    def _handle(self, dat:WorkingData) -> None:
        if not self.file_read and self.file_iter is None:
            auto_file = AutoInputFileIterable(self.file_path, 'rb', dat.newline)
            try:
                self.file_iter = iter(auto_file)
            except OSError:
                # Ignore file
                self.file_read = True
                self.file_iter = None

        if self.file_iter:
            try:
                next_line = next(self.file_iter)
            except StopIteration:
                self.file_read = True
                self.file_iter = None
            else:
                dat.append(next_line, add_newline=False)

    @staticmethod
    def from_string(condition:SedCondition, s):
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            s.advance(1)
            s.advance_past()
            s.mark()
            # Semicolons are considered part of the file name string
            s.advance_end()
            return AppendLineFromFile(condition, s.str_from_mark())
        else:
            raise SedParsingException('Not an append line from file command sequence')

class TestBranchCommand(SedCommand):
    COMMAND_CHAR = 't'

    def __init__(self, condition: SedCondition, branch_name=''):
        super().__init__(condition)
        self._branch_name = branch_name

    def _handle(self, dat:WorkingData) -> None:
        if dat.pattern_modified and self._branch_name:
            dat.jump_to = self._branch_name

    @staticmethod
    def from_string(condition:SedCondition, s):
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            s.advance(1)
            s.advance_past()
            s.mark()
            s.advance_until(SOMETIMES_END_CMD_CHAR)
            branch_name = s.str_from_mark()
            return TestBranchCommand(condition, branch_name)
        else:
            raise SedParsingException('Not a test branch sequence')

class TestBranchNotCommand(SedCommand):
    COMMAND_CHAR = 'T'

    def __init__(self, condition: SedCondition, branch_name=''):
        super().__init__(condition)
        self._branch_name = branch_name

    def _handle(self, dat:WorkingData) -> None:
        if not dat.pattern_modified and self._branch_name:
            dat.jump_to = self._branch_name

    @staticmethod
    def from_string(condition:SedCondition, s):
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            s.advance(1)
            s.advance_past()
            s.mark()
            s.advance_until(SOMETIMES_END_CMD_CHAR)
            branch_name = s.str_from_mark()
            return TestBranchNotCommand(condition, branch_name)
        else:
            raise SedParsingException('Not a test branch not sequence')

class VersionCommand(SedCommand):
    COMMAND_CHAR = 'v'

    @staticmethod
    def from_string(condition:SedCondition, s):
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            s.advance(1)
            s.advance_past()
            s.mark()
            s.advance_until(SOMETIMES_END_CMD_CHAR)
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
        else:
            raise SedParsingException('Not a version sequence')

class WritePatternCommand(SedCommand):
    COMMAND_CHAR = 'w'

    def __init__(self, condition: SedCondition, file_path) -> None:
        super().__init__(condition)
        self._out_file = _filename_to_writer(file_path)

    def _handle(self, dat:WorkingData) -> None:
        self._out_file.write(dat.pattern_space)
        self._out_file.flush()

    @staticmethod
    def from_string(condition:SedCondition, s):
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
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

    def __init__(self, condition: SedCondition, file_path) -> None:
        super().__init__(condition)
        self._out_file = _filename_to_writer(file_path)

    def _handle(self, dat:WorkingData) -> None:
        loc = dat.pattern_space.find(dat.newline)
        if loc < 0:
            self._out_file.write(dat.pattern_space)
        else:
            self._out_file.write(dat.pattern_space[:loc+1])
        self._out_file.flush()

    @staticmethod
    def from_string(condition:SedCondition, s):
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            s.advance(1)
            s.advance_past()
            s.mark()
            # Semicolons are considered part of the file name string
            s.advance_end()
            return WritePatternCommand(condition, s.str_from_mark())
        else:
            raise SedParsingException('Not a write pattern command sequence')

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
            s.advance_until(SOMETIMES_END_CMD_CHAR)
            label = s.str_from_mark()
            return Label(condition, label)
        else:
            raise SedParsingException('Not a label')

class Comment(SedCommand):
    COMMAND_CHAR = '#'

    def __init__(self, condition: SedCondition):
        super().__init__(condition)

    @staticmethod
    def from_string(condition:SedCondition, s):
        if isinstance(s, str):
            s = StringParser(s)

        if s.advance_past() and s[0] == __class__.COMMAND_CHAR:
            s.advance_end()
            return None
        else:
            raise SedParsingException('Not a comment')

SED_COMMANDS = {
    SubstituteCommand.COMMAND_CHAR: SubstituteCommand,
    AppendCommand.COMMAND_CHAR: AppendCommand,
    BranchCommand.COMMAND_CHAR: BranchCommand,
    ReplaceCommand.COMMAND_CHAR: ReplaceCommand,
    DeleteCommand.COMMAND_CHAR: DeleteCommand,
    DeleteToNewlineCommand.COMMAND_CHAR: DeleteToNewlineCommand,
    ExecuteCommand.COMMAND_CHAR: ExecuteCommand,
    FileCommand.COMMAND_CHAR: FileCommand,
    SetHoldspace.COMMAND_CHAR: SetHoldspace,
    AppendHoldspace.COMMAND_CHAR: AppendHoldspace,
    SetFromHoldspace.COMMAND_CHAR: SetFromHoldspace,
    AppendFromHoldspace.COMMAND_CHAR: AppendFromHoldspace,
    InsertCommand.COMMAND_CHAR: InsertCommand,
    UnambiguousPrint.COMMAND_CHAR: UnambiguousPrint,
    NextCommand.COMMAND_CHAR: NextCommand,
    AppendNextCommand.COMMAND_CHAR: AppendNextCommand,
    PrintCommand.COMMAND_CHAR: PrintCommand,
    PrintToNewlineCommand.COMMAND_CHAR: PrintToNewlineCommand,
    QuitCommand.COMMAND_CHAR: QuitCommand,
    QuitWithoutPrintCommand.COMMAND_CHAR: QuitWithoutPrintCommand,
    AppendFileContents.COMMAND_CHAR: AppendFileContents,
    AppendLineFromFile.COMMAND_CHAR: AppendLineFromFile,
    TestBranchCommand.COMMAND_CHAR: TestBranchCommand,
    TestBranchNotCommand.COMMAND_CHAR: TestBranchNotCommand,
    VersionCommand.COMMAND_CHAR: VersionCommand,
    WritePatternCommand.COMMAND_CHAR: WritePatternCommand,
    WritePatternToNewlineCommand.COMMAND_CHAR: WritePatternToNewlineCommand,
    Label.COMMAND_CHAR: Label,
    Comment.COMMAND_CHAR: Comment
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
        script_lines = script.split(ALWAYS_END_CMD_CHAR)
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
                # Remove escaping char, glue the next one to the end of this one, and then delete next
                script_lines[i] = script_lines[i][:-1] + script_lines[i+1]
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

                    if substr_line.advance_past() and substr_line[0] not in SOMETIMES_END_CMD_CHAR:
                        command_type = SED_COMMANDS.get(substr_line[0], None)

                        if command_type is None:
                            raise SedParsingException(f'Invalid command: {substr_line[0]}')

                        command = command_type.from_string(condition, substr_line)

                        if substr_line.advance_past() and substr_line[0] not in SOMETIMES_END_CMD_CHAR:
                            raise SedParsingException(f'extra characters after command')

                        substr_line.advance_past(WHITESPACE_CHARS + SOMETIMES_END_CMD_CHAR)

                        if command is not None:
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
            files = [StdinIterable(end=self.newline, label='-')]
        else:
            files = [AutoInputFileIterable(f, newline_str=self.newline) for f in self._files]

        dat = WorkingData()
        dat.newline = self.newline
        for file in files:
            dat.set_in_file(file)

            if self.in_place and not isinstance(file, StdinIterable):
                # Write to temporary file to be copied to target when it changes
                tmp_file = tempfile.NamedTemporaryFile(mode='wb')
                dat.out_file = tmp_file
            else:
                tmp_file = None
                dat.out_file = sys.stdout.buffer

            while dat.next_line():
                i = 0
                while i < len(self._commands):
                    command = self._commands[i]
                    i += 1

                    try:
                        command.handle(dat)
                    except SedQuitException as ex:
                        return ex.exit_code

                    if dat.pattern_space is None:
                        # This will happen if a next command was used, and there is nothing else to read
                        break
                    # Command may set jump_to when we need to jump to another command
                    elif dat.jump_to is not None:
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
                dat.flush_all_data()

            # Final pattern flush just in case there was something left
            dat.flush_all_data()

            if dat.file_modified and tmp_file:
                # Write data from temp file to destination
                tmp_file.flush()
                file_name = os.path.abspath(file.name)
                if self.in_place_backup_suffix is not None:
                    backup_name = file_name + self.in_place_backup_suffix
                    shutil.copy2(file_name, backup_name)
                os.remove(file_name)
                shutil.copy2(tmp_file.name, file_name)
                del tmp_file
        return 0

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
        return sed.execute()
    except Exception as ex:
        if args.verbose:
            raise ex
        else:
            print(f'{PACKAGE_NAME}: {ex}', file=sys.stderr)
            return 1
