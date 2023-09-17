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
from .commands import *

import os
import sys
import argparse
import shutil
import glob
from io import BytesIO
from typing import Any, Union, List, BinaryIO
from .utils import __version__, PACKAGE_NAME, IS_WINDOWS

class Sed:
    def __init__(self):
        self._commands = SedCommandGroup(None)
        self._expression_number = 0
        self._files = []
        self._newline:bytes = b'\n'
        # Parse files in place instead of to stdout
        self.in_place:bool = False
        # The suffix to use for creating backup files when in_place is True
        self.in_place_backup_suffix:Union[str,None] = None
        # When True, follow symbolic links when in_place is True
        self.follow_symlinks:bool = False
        # True to suppress printing of pattern space
        self.suppress_pattern_print:bool = False
        # True to use extended regex mode
        self.extended_regex:bool = False
        # The line length to use for l command
        self.unambiguous_line_len:int = 70
        # When true, restart line count when a new file is opened
        self.separate:bool = False
        # Disable e/r/w commands when True
        self.sandbox_mode:bool = False

    @property
    def newline(self) -> bytes:
        ''' Returns the newline sequence the input data is split by '''
        return self._newline

    @newline.setter
    def newline(self, newline:Union[str,bytes]):
        if isinstance(newline, str):
            self._newline = newline.encode()
        else:
            self._newline = newline

    def add_expression(self, script:str) -> None:
        '''
        Adds an expression string (i.e. a command line expression string).
        Expressions are parsed and added to my internal list of commands.
        '''
        self._expression_number += 1
        self._commands.add_expression(script, self._expression_number, self.sandbox_mode)

    def add_command(self, command_or_commands:Union[SedCommand, List[SedCommand]]) -> None:
        ''' Adds a command object or list of commands (one of SedCommand)'''
        self._commands.add_commands(command_or_commands)

    def clear_commands(self) -> None:
        ''' Clears all set commands and expressions '''
        self._commands.clear_commands()
        self._expression_number = 0

    def add_file(self, file_or_files:Union[str, List[str]]) -> None:
        ''' Adds a file to parse '''
        if isinstance(file_or_files, list):
            self._files.extend(file_or_files)
        else:
            self._files.append(file_or_files)

    def clear_files(self) -> None:
        ''' Clears all files set by add_file '''
        self._files.clear()

    def execute(self, out_buffer:BinaryIO=sys.stdout.buffer) -> int:
        '''
        Executes Sed with the settings, commands, and files set.
        Inputs: out_buffer - when in_place is false, this is the buffer written to (stdout by default)
        Returns the exit code (0 on success)
        '''
        self._commands.check_labels()

        if not self._files:
            files = [StdinIterable(end=self.newline, label='-')]
        else:
            files = [AutoInputFileIterable(f, newline_str=self.newline) for f in self._files]

        dat = WorkingData()
        dat.suppress_pattern_print = self.suppress_pattern_print
        dat.extended_regex = self.extended_regex
        dat.unambiguous_line_len = self.unambiguous_line_len
        dat.separate = self.separate
        dat.newline = self.newline
        for file in files:
            dat.set_in_file(file)

            if self.in_place and not isinstance(file, StdinIterable):
                # Write to temporary file to be copied to target when it changes
                tmp_file = BytesIO()
                dat.out_file = tmp_file
            else:
                tmp_file = None
                dat.out_file = out_buffer

            while dat.next_line():
                # Start at the beginning
                dat.jump_to = 0
                try:
                    while dat.jump_to is not None:
                        jump_to = dat.jump_to
                        dat.jump_to = None
                        # jump_to may be -1, 0, or label
                        if jump_to == 0:
                            # Jump to beginning
                            self._commands.handle(dat)
                        elif isinstance(jump_to, str):
                            if not self._commands.jump_to_label(dat, jump_to):
                                # Shouldn't reach here due to self._commands.check_labels() above
                                raise SedExecutionException(f"can't find label for jump to `{jump_to}'")
                        # else: jump to end (flush and read next line)
                except SedQuitException as ex:
                    return ex.exit_code
                except SedFileCompleteException:
                    # This will happen if a next command was used, and there is nothing else to read
                    break

                dat.flush_all_data()

            # Final pattern flush just in case there was something left
            dat.flush_all_data()

            if dat.file_modified and tmp_file:
                # Write data from temp file to destination
                tmp_file.flush()
                if self.follow_symlinks:
                    file_name = os.path.abspath(os.path.realpath(file.name))
                else:
                    file_name = os.path.abspath(file.name)
                if self.in_place_backup_suffix is not None:
                    backup_name = file_name + self.in_place_backup_suffix
                    shutil.copy2(file_name, backup_name)
                with open(file_name, 'wb') as fp:
                    fp.write(tmp_file.getvalue())
        return 0

def parse_args(cliargs:List[str]):
    ''' Parses all arguments from command line '''
    parser = argparse.ArgumentParser(
        prog=PACKAGE_NAME,
        description='A sed clone in Python with both CLI and library interfaces'
    )

    parser.add_argument('script', type=str, nargs='?', default=None,
                        help='script, only if no other script defined below')
    parser.add_argument('input_file', metavar='input-file', type=str, nargs='*', default=[],
                        help='Input file(s) to parse')

    parser.add_argument('-n', '--quiet', '--silent', dest='quiet', action='store_true',
                        help='suppress automatic printing of pattern space')
    # No debug data
    parser.add_argument('--debug', action='store_true', help='annotate program execution')
    parser.add_argument('-e', '--expression', metavar='script', type=str, default=[], action='append',
                        help='add the script to the commands to be executed')
    parser.add_argument('-f', '--file', metavar='script-file', type=str, default=[], action='append',
                        help='add the contents of script-file to the commands to be executed')
    parser.add_argument('--follow-symlinks', action='store_true',
                        help='follow symlinks when processing in place')
    parser.add_argument('-i', '--in-place', metavar='SUFFIX', nargs='?', type=str, default=None,
                        const=True,
                        help='edit files in place (makes backup if SUFFIX supplied)')
    parser.add_argument('-l', '--line-length', metavar='N', type=int, default=70,
                        help='specify the desired line-wrap length for the `l\' command')
    # This option currently has no effect
    parser.add_argument('--posix', action='store_true', help='disable all extensions.')
    parser.add_argument('-E', '-r', '--regexp-extended', action='store_true',
                        help='use extended regular expressions in the script')
    parser.add_argument('-s', '--separate', action='store_true',
                        help='consider files as separate rather than as a single, '
                        'continuous long stream.')
    parser.add_argument('--sandbox', action='store_true',
                        help='operate in sandbox mode (disable e/r/w commands).')
    # This is just done by default - here for compatibility only
    parser.add_argument('-u', '--unbuffered', action='store_true',
                        help='load minimal amounts of data from the input files and flush '
                        'the output buffers more often')
    parser.add_argument('--end', type=str, default='\n',
                        help='end-of-line character for parsing search files (default: \\n); '
                        'this does not affect file parsing for -f or --exclude-from')
    parser.add_argument('-z', '--null-data', action='store_true',
                        help='same as --end=\'\\0\'')
    parser.add_argument('--version', action='store_true',
                        help='output version information and exit')
    parser.add_argument('--verbose', action='store_true', help='show verbose errors')
    args = parser.parse_args(cliargs)

    if args.expression or args.file:
        # The first positional is instead an input file
        if args.script is not None:
            args.input_file.insert(0, args.script)
            args.script = None
    elif args.script is None and not args.version:
        parser.print_help()
        sys.exit(1)

    return args

def _expand_cli_path(path:str) -> List[str]:
    if IS_WINDOWS and '*' in path or '?' in path:
        # Need to manually expand this out
        expanded_paths = [f for f in glob.glob(path)]
        if not expanded_paths:
            print('No match for: {}'.format(path), file=sys.stderr)
    else:
        # *nix and *nix based systems do this from command line
        expanded_paths = [path]
    return expanded_paths

def _expand_cli_paths(paths:List[str]) -> List[str]:
    return [y for x in paths for y in _expand_cli_path(x)]

def main(cliargs:List[str]) -> int:
    ''' Command line main execution point '''
    args = parse_args(cliargs)
    if args.version:
        print('{} {}'.format(PACKAGE_NAME, __version__))
        return 0

    sed = Sed()

    try:
        sed.suppress_pattern_print = args.quiet
        sed.extended_regex = args.regexp_extended
        sed.unambiguous_line_len = args.line_length
        sed.separate = args.separate
        sed.sandbox_mode = args.sandbox
        sed.follow_symlinks = args.follow_symlinks
        if args.null_data:
            sed.newline = '\0'
        else:
            sed.newline = bytes(args.end, "utf-8").decode("unicode_escape")
        if args.script:
            sed.add_expression(args.script)
        for expression in args.expression:
            sed.add_expression(expression)
        for file in _expand_cli_paths(args.file):
            with open(file, 'r') as fp:
                sed.add_expression(fp.read())
        if args.input_file:
            sed.add_file(_expand_cli_paths(args.input_file))
        if args.in_place is not None:
            sed.in_place = True
            if isinstance(args.in_place, str):
                sed.in_place_backup_suffix = args.in_place
        return sed.execute(sys.stdout.buffer)
    except Exception as ex:
        if args.verbose:
            raise ex
        else:
            print(f'{PACKAGE_NAME}: {ex}', file=sys.stderr)
            return 1
