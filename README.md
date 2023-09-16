# sedeuce

A seductive sed clone in Python with both CLI and library interfaces

## Known Differences with sed

- Substitute
    - The Python module re is internally used for all regular expressions. The inputted regular
    expression is modified only when basic regular expressions are used.
    - The m/M modifier will act differently due to how Python re handles multiline mode
    - GNU sed extension special sequences not supported
- Newline can always be escaped with \ in any command

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