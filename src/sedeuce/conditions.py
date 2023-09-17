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

from .utils import *

import re
from typing import Any, Union, List

class SedCondition:
    def is_match(self, dat:WorkingData) -> bool:
        return False

class StaticSedCondition(SedCondition):
    def __init__(self, static_value:bool) -> None:
        super().__init__()
        self._static_value = static_value

    def is_match(self, dat:WorkingData) -> bool:
        return self._static_value

class RangeSedCondition(SedCondition):
    def __init__(self, start_line:int, end_line:int=None) -> None:
        super().__init__()
        self._start_line = start_line
        if end_line is not None:
            self._end_line = end_line
        else:
            self._end_line = start_line

    def is_match(self, dat:WorkingData) -> bool:
        return dat.line_number >= self._start_line and dat.line_number <= self._end_line

    @staticmethod
    def from_string(s:Union[str,StringParser]) -> SedCondition:
        if isinstance(s, str):
            s = StringParser(s)

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
    def __init__(self, pattern:Union[str,bytes]) -> None:
        super().__init__()
        self._pattern = pattern
        if isinstance(self._pattern, str):
            self._pattern = self._pattern.encode()
        self._extended_regex = True

    def is_match(self, dat:WorkingData) -> bool:
        if dat.extended_regex != self._extended_regex:
            self._pattern = pattern_escape_invert(self._pattern, '+?|{}()')
            self._extended_regex = not self._extended_regex
        return (re.search(self._pattern, dat.pattern_space) is not None)

    @staticmethod
    def from_string(s:Union[str,StringParser]) -> SedCondition:
        if isinstance(s, str):
            s = StringParser(s)

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