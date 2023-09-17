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

from .sed import Sed

from .conditions import StaticSedCondition, RangeSedCondition, RegexSedCondition

from .commands import (
    SubstituteCommand,
    AppendCommand,
    BranchCommand,
    ReplaceCommand,
    DeleteCommand,
    DeleteToNewlineCommand,
    ExecuteCommand,
    FileCommand,
    SetHoldspaceCommand,
    AppendHoldspaceCommand,
    SetFromHoldspaceCommand,
    AppendFromHoldspaceCommand,
    InsertCommand,
    UnambiguousPrintCommand,
    NextCommand,
    AppendNextCommand,
    PrintCommand,
    PrintToNewlineCommand,
    QuitCommand,
    QuitWithoutPrintCommand,
    AppendFileContentsCommand,
    AppendLineFromFileCommand,
    TestBranchCommand,
    TestBranchNotCommand,
    VersionCommand,
    WritePatternCommand,
    WritePatternToNewlineCommand,
    ExchangeCommand,
    TranslateCommand,
    ZapCommand,
    CommentCommand,
    PrintLineNumberCommand,
    LabelCommand,
    SED_COMMAND_LOOKUP
)
