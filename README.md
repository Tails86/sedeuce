# sedeuce

A seductive sed clone in Python with both CLI and library interfaces

## Known Differences with sed

- The Python module `re` is internally used for all regular expressions. The inputted regular
    expression is modified only when basic regular expressions are used in order to reverse meaning
    of for escaped characters `+?|{}()`
- Substitute
    - The m/M modifier will act differently due to how Python re handles multiline mode
    - GNU sed extension special sequences not supported
    - All `\n` characters match with $ (end of line) due to use of Python `re`
- Newline can always be escaped with \ in any command

## Contribution

Feel free to open a bug report or make a merge request on [github](https://github.com/Tails86/sedeuce/issues).

## Installation
This project is uploaded to PyPI at https://pypi.org/project/sedeuce/

To install, ensure you are connected to the internet and execute: `python3 -m pip install sedeuce --upgrade`

Once installed, there will be a script called `sedeuce` under Python's script directory. If `sed`
is not found on the system, then a script called `sed` will also be installed. Ensure Python's
scripts directory is under the environment variable `PATH` in order to be able to execute the script
properly from command line.

## CLI Help

```
usage: sedeuce [-h] [-n] [--debug] [-e script] [-f script-file]
               [--follow-symlinks] [-i [SUFFIX]] [-l N] [--posix] [-E] [-s]
               [--sandbox] [-u] [--end END] [-z] [--version] [--verbose]
               [script] [input-file [input-file ...]]

A sed clone in Python with both CLI and library interfaces

positional arguments:
  script                script, only if no other script defined below
  input-file            Input file(s) to parse

optional arguments:
  -h, --help            show this help message and exit
  -n, --quiet, --silent
                        suppress automatic printing of pattern space
  --debug               annotate program execution
  -e script, --expression script
                        add the script to the commands to be executed
  -f script-file, --file script-file
                        add the contents of script-file to the commands to be
                        executed
  --follow-symlinks     follow symlinks when processing in place
  -i [SUFFIX], --in-place [SUFFIX]
                        edit files in place (makes backup if SUFFIX supplied)
  -l N, --line-length N
                        specify the desired line-wrap length for the `l'
                        command
  --posix               disable all extensions.
  -E, -r, --regexp-extended
                        use extended regular expressions in the script
  -s, --separate        consider files as separate rather than as a single,
                        continuous long stream.
  --sandbox             operate in sandbox mode (disable e/r/w commands).
  -u, --unbuffered      load minimal amounts of data from the input files and
                        flush the output buffers more often
  --end END             end-of-line character for parsing search files
                        (default: \n); this does not affect file parsing for -f
                        or --exclude-from
  -z, --null-data       same as --end='\0'
  --version             output version information and exit
  --verbose             show verbose errors
```

## Library Help

sedeuce can be used as a library from another module. The following is a simple example.

```py
import sedeuce
from io import BytesIO
# Create sed object
sed = sedeuce.Sed()
# Set all desired sed settings
sed.extended_regex = True
# Add commands
sed.add_command(sedeuce.SubstituteCommand(None, '([0-9]+)', 'Numbers: \\1'))
# Add files to parse
sed.add_file('path/to/file.txt')
# In this example, parsed data is captured by a BytesIO object
byte_buffer = BytesIO()
# Execute sed parsing with above settings and data
sed.execute(byte_buffer)
# Print the result
print(byte_buffer.getvalue().decode())
```

The following Sed methods may be called to add expressions, commands, and files.

```py
add_expression(self, script:str) -> None:
  '''
  Adds an expression string (i.e. a command line expression string).
  Expressions are parsed and added to my internal list of commands.
  '''

add_command(self, command_or_commands:Union[SedCommand, List[SedCommand]]) -> None:
  ''' Adds a command object or list of commands (one of SedCommand)'''

clear_commands(self) -> None:
  ''' Clears all set commands and expressions '''

add_file(self, file_or_files:Union[str, List[str]]) -> None:
  ''' Adds a file to parse '''

clear_files(self) -> None:
  ''' Clears all files set by add_file '''
```

The following Sed options may be adjusted.

```py
# (property) The sequence of bytes expected at the end of each line
# Returns bytes, can be set as str or bytes
newline = b'\n'

# Parse files in place instead of to stdout
in_place:bool = False

# The suffix to use for creating backup files when in_place is True
in_place_backup_suffix:Union[str,None] = None

# When True, follow symbolic links when in_place is True
follow_symlinks:bool = False

# True to suppress printing of pattern space
suppress_pattern_print:bool = False

# True to use extended regex mode
extended_regex:bool = False

# The line length to use for l command
unambiguous_line_len:int = 70

# When True, restart line count when a new file is opened
separate:bool = False

# Disable e/r/w commands when True
sandbox_mode:bool = False
```