# sedeuce
A sed clone in Python with both CLI and library interfaces

## Current Support

- Can input script string from command line
    - Line range and regex conditions are supported
    - Substitute command is supported (except for special sequence characters in replace string i.e. \l \L \u \U \E)
- Can optionally input file list from command line
    - Read from stdin is supported if no files given
- Option -i, --in-place supported

## Known Differences with sed

- Substitute
    - The Python module re is internally used for all regular expressions. The inputted regular
    expression is modified only when basic regular expressions are used.
    - The m/M modifier will act differently due to how Python re handles multiline mode

## Development Roadmap

- Support for special sequence characters in substitute command
- Support all or most of the SED script commands
- Support all options
- Add custom line identifier option input
- Implement unit tests for all features
- Add CI workflow

## CLI Help

```
usage: sedeuce [-h] [-i [SUFFIX]] [--version] [--verbose] [script]
               [input-file [input-file ...]]

A sed clone in Python with both CLI and library interfaces

positional arguments:
  script                script, only if no other script defined below
  input-file            Input file(s) to parse

optional arguments:
  -h, --help            show this help message and exit
  -i [SUFFIX], --in-place [SUFFIX]
                        edit files in place (makes backup if SUFFIX supplied)
  --version             output version information and exit
  --verbose             show verbose errors

NOTE: Only substitute command is currently available
```