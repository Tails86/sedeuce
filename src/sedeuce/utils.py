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
import threading
from typing import Any, Union, List

__version__ = '1.0.2'
PACKAGE_NAME = 'sedeuce'

VERSION_PARTS = [int(i) for i in __version__.split('.')]

IS_WINDOWS = sys.platform.lower().startswith('win')

# sed syntax
# \n (newline) always separates one command from the next unless proceeded by a slash: \
# ; usually separates one command from the next, but it depends on the command

WHITESPACE_CHARS = (' \t\r\n\v\f\u0020\u00A0\u1680\u2000\u2001\u2002\u2003\u2004'
                    '\u2005\u2006\u2007\u2008\u2009\u200A\u202F\u205F\u3000')
NUMBER_CHARS = '0123456789'
SOMETIMES_END_CMD_CHARS = ';}'
ALWAYS_END_CMD_CHAR = '\n'

class SedParsingException(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)

class SedExecutionException(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)

class SedQuitException(Exception):
    def __init__(self, exit_code:int) -> None:
        super().__init__()
        self.exit_code = exit_code

class SedFileCompleteException(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)

def pattern_escape_invert(pattern, chars):
    if isinstance(pattern, bytes):
        if isinstance(chars, str):
            chars = chars.encode()
        escape = b'\\'
    else:
        if isinstance(chars, bytes):
            chars = chars.decode()
        escape = '\\'

    for char in chars:
        if isinstance(char, int):
            # convert the char back to bytes
            char = char.to_bytes(1, byteorder='little')
        escaped_char = escape + char
        pattern = char.join([piece.replace(char, escaped_char) for piece in pattern.split(escaped_char)])
    return pattern

class StringParser:
    ''' Contains a string and an advancing position pointer '''

    def __init__(self, s='', pos=0, char_offset=0):
        self.set(s, pos)
        self.char_offset = char_offset
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

    @property
    def pos_offset(self):
        return self.pos + self.char_offset

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
            start = val.start
            stop = val.stop
            if val.start is not None:
                start += offset
            if val.stop is not None:
                stop += offset
            val = slice(start, stop, val.step)
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

def filename_to_writer(file_name):
    if file_name == '/dev/stdout':
        return sys.stdout.buffer
    elif file_name == '/dev/stderr':
        return sys.stderr.buffer
    else:
        return SharedFileWriter(file_name, binary=True, append=False)

def count_end_escapes(s:str):
    count = 0
    for c in reversed(s):
        if c == '\\':
            count += 1
        else:
            break
    return count

def _string_to_splitter(s:StringParser, splitter):
    s.mark()
    if not s.advance_until(splitter):
        return None
    current_str = s.str_from_mark()
    # If there are an odd number of slashes at the end of the string,
    # then next newline was escaped;
    # ex: \ escapes next \\ just means slash and \\\ means slash plus escape next
    while count_end_escapes(current_str) % 2 == 1:
        # Remove the escape
        current_str = current_str[:-1]
        s.mark()
        s.advance(1)
        if not s.advance_until(splitter):
            return None
        current_str += s.str_from_mark()

    return current_str

def dual_field_command_parse(s):
    if isinstance(s, str):
        s = StringParser(s)

    splitter = s[0]
    s.advance(1)
    first = _string_to_splitter(s, splitter)
    if first is None:
        return (None, None)
    s.advance(1)
    second = _string_to_splitter(s, splitter)
    if second is None:
        return (first, None)
    s.advance(1)
    return (first, second)

class WorkingData:
    def __init__(self) -> None:
        self.suppress_pattern_print = False
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
        self.jump_to = None # should be None, 0, -1, or string
        self.holdspace = b''
        self.extended_regex = False
        self.unambiguous_line_len = 70
        self.separate = False

    def set_in_file(self, file:FileIterable):
        self.file_modified = False
        self.in_file = file
        # This will raise an exception if file could not be opened
        self.in_file_iter = iter(self.in_file)
        if self.separate:
            self.line_number = 0

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
            self._pattern_space = None
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
            self._pattern_space = None
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
            if not self.suppress_pattern_print:
                # Write the modified pattern space
                self._write(self.pattern_space)
            else:
                self.file_modified = True
            self._pattern_space = None
            self.pattern_modified = False

        self._flush_append_data()
