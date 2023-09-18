#!/usr/bin/env python3

import os
import sys
import unittest
from io import BytesIO, StringIO
from unittest.mock import patch
import tempfile

THIS_FILE_PATH = os.path.dirname(os.path.abspath(os.path.realpath(__file__)))
PROJECT_DIR = os.path.abspath(os.path.join(THIS_FILE_PATH, '..'))
SOURCE_DIR = os.path.abspath(os.path.join(PROJECT_DIR, 'src'))

sys.path.insert(0, SOURCE_DIR)
from sedeuce import sed

# Some stream of conscience
test_file1 = '''this is a file
which contains several lines,
and I am am am using
it to test
sed for a while

here is some junk text
dlkjfkldsjf
dsfklaslkdjfa sedf;l asjd
fasjd f ;8675309
;ajsdfj sdljf ajsdfj;sdljf
ajsdfja;sjdf ;sdajf ;l'''

def _is_windows():
    return sys.platform.lower().startswith('win')

class FakeStdOut:
    def __init__(self) -> None:
        self.buffer = BytesIO()

class FakeStdIn:
    def __init__(self, loaded_str):
        if isinstance(loaded_str, str):
            loaded_str = loaded_str.encode()
        self.buffer = BytesIO(loaded_str)

class CliTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.TemporaryDirectory()
        with open(os.path.join(cls.tmpdir.name, "file1.txt"), "wb") as fd:
            fd.write(test_file1.encode())
        with open(os.path.join(cls.tmpdir.name, "numbers.txt"), "wb") as fd:
            fd.write(b'0\n1\n2\n3\n4\n5\n6\n7\n8\n9')

    def setUp(self):
        self.old_dir = os.getcwd()
        os.chdir(self.tmpdir.name)

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir.cleanup()

    def tearDown(self):
        os.chdir(self.old_dir)

    def test_no_substitute_no_match(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out, \
            patch('sedeuce.sed.sys.stdin', FakeStdIn(test_file1)) \
        :
            sed.main(['s/this will not match/this will never print/'])

            out_lines = test_file1.split('\n')
            in_lines = fake_out.buffer.getvalue().decode().split('\n')

        self.assertEqual(in_lines, out_lines)

    def test_substitute_basic_in_range(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out, \
            patch('sedeuce.sed.sys.stdin', FakeStdIn(test_file1)) \
        :
            sed.main(['1,3s/am/sam;/'])

            out_lines = test_file1.split('\n')
            in_lines = fake_out.buffer.getvalue().decode().split('\n')

        self.assertEqual(len(in_lines), len(out_lines))
        self.assertEqual(in_lines[2], 'and I sam; am am using')
        del in_lines[2]
        del out_lines[2]
        self.assertEqual(in_lines, out_lines)

    def test_substitute_basic_in_regex(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out, \
            patch('sedeuce.sed.sys.stdin', FakeStdIn(test_file1)) \
        :
            sed.main(['/and/ s/am/sam;/'])

            out_lines = test_file1.split('\n')
            in_lines = fake_out.buffer.getvalue().decode().split('\n')

        self.assertEqual(len(in_lines), len(out_lines))
        self.assertEqual(in_lines[2], 'and I sam; am am using')

    def test_substitute_basic_out_of_range(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out, \
            patch('sedeuce.sed.sys.stdin', FakeStdIn(test_file1)) \
        :
            sed.main(['1,2s/am/sam;/'])

            out_lines = test_file1.split('\n')
            in_lines = fake_out.buffer.getvalue().decode().split('\n')

        self.assertEqual(len(in_lines), len(out_lines))
        self.assertEqual(in_lines[2], 'and I am am am using')

    def test_substitute_basic_out_of_regex(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out, \
            patch('sedeuce.sed.sys.stdin', FakeStdIn(test_file1)) \
        :
            sed.main(['/[0-9]+/s/am/sam;/'])

            out_lines = test_file1.split('\n')
            in_lines = fake_out.buffer.getvalue().decode().split('\n')

        self.assertEqual(len(in_lines), len(out_lines))
        self.assertEqual(in_lines[2], 'and I am am am using')

    def test_substitute_global_in_range(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out, \
            patch('sedeuce.sed.sys.stdin', FakeStdIn(test_file1)) \
        :
            # Spaces after the last substitute marker should be ignored around ' g '
            sed.main(['3s/am/sam;/ g '])

            out_lines = test_file1.split('\n')
            in_lines = fake_out.buffer.getvalue().decode().split('\n')

        self.assertEqual(len(in_lines), len(out_lines))
        self.assertEqual(in_lines[2], 'and I sam; sam; sam; using')

    def test_substitute_replace_sequences(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out, \
            patch('sedeuce.sed.sys.stdin', FakeStdIn(test_file1)) \
        :
            sed.main(['s=.*;\\([0-9]\\{3\\}\\)\\([0-9]\\{4\\}\\)=I got your number: \\1-\\2 (I got it)='])

            out_lines = test_file1.split('\n')
            in_lines = fake_out.buffer.getvalue().decode().split('\n')

        self.assertEqual(len(in_lines), len(out_lines))
        self.assertEqual(in_lines[9], 'I got your number: 867-5309 (I got it)')

    def test_substitute_number(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out, \
            patch('sedeuce.sed.sys.stdin', FakeStdIn(test_file1)) \
        :
            sed.main(['3s/am/sam;/2'])

            out_lines = test_file1.split('\n')
            in_lines = fake_out.buffer.getvalue().decode().split('\n')

        self.assertEqual(len(in_lines), len(out_lines))
        self.assertEqual(in_lines[2], 'and I am sam; am using')

    def test_substitute_number_plus_global(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out, \
            patch('sedeuce.sed.sys.stdin', FakeStdIn(test_file1)) \
        :
            sed.main(['3s/am/sam;/2g'])

            out_lines = test_file1.split('\n')
            in_lines = fake_out.buffer.getvalue().decode().split('\n')

        self.assertEqual(len(in_lines), len(out_lines))
        self.assertEqual(in_lines[2], 'and I am sam; sam; using')

    def test_substitute_print(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out, \
            patch('sedeuce.sed.sys.stdin', FakeStdIn(test_file1)) \
        :
            sed.main(['3s/am/sam;/p'])

            in_lines = fake_out.buffer.getvalue().decode().split('\n')

        self.assertGreater(len(in_lines), 3)
        # Once for the regular output
        self.assertEqual(in_lines[2], 'and I sam; am am using')
        # match found, so it it also printed
        self.assertEqual(in_lines[3], 'and I sam; am am using')

    def test_substitute_write_stdout(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out, \
            patch('sedeuce.sed.sys.stdin', FakeStdIn(test_file1)) \
        :
            sed.main(['3s/am/sam;/w /dev/stdout'])

            in_lines = fake_out.buffer.getvalue().decode().split('\n')

        self.assertGreater(len(in_lines), 3)
        # Once for the regular output
        self.assertEqual(in_lines[2], 'and I sam; am am using')
        # match found, so it it also printed
        self.assertEqual(in_lines[3], 'and I sam; am am using')

    def test_substitute_write_file(self):
        tmp_dir = tempfile.TemporaryDirectory()
        try:
            file_path = os.path.join(tmp_dir.name, 'file.txt')
            with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out, \
                patch('sedeuce.sed.sys.stdin', FakeStdIn(test_file1)) \
            :
                sed.main([f'3s/am/sam;/w {file_path}'])

            with open(file_path, 'r') as fp:
                in_tmp = list(fp.readlines())
            self.assertEqual(len(in_tmp), 1)
            self.assertEqual(in_tmp[0], 'and I sam; am am using\n')
        finally:
            tmp_dir.cleanup()

    @unittest.skipIf(_is_windows(), "can't execute multiplication from default command line in Windows")
    def test_substitute_number_plus_execute(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out, \
            patch('sedeuce.sed.sys.stdin', FakeStdIn('xyz\n9876 1234\nabcd')) \
        :
            # This finds 1234 and executes "echo $((43 * 21))" for that match
            sed.main(['s=\\([0-9]\\)\\([0-9]\\)\\([0-9]\\)\\([0-9]\\)=echo $((\\4\\3 * \\2\\1))=2e'])

            in_lines = fake_out.buffer.getvalue().decode().split('\n')

        self.assertEqual(in_lines, ['xyz', '9876 903', 'abcd'])

    def test_substitute_ignore_case(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out, \
            patch('sedeuce.sed.sys.stdin', FakeStdIn(test_file1)) \
        :
            sed.main(['s/AM/sam;/i'])

            in_lines = fake_out.buffer.getvalue().decode().split('\n')

        self.assertGreater(len(in_lines), 2)
        self.assertEqual(in_lines[2], 'and I sam; am am using')

    def test_substitute_multiline(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out, \
            patch('sedeuce.sed.sys.stdin', FakeStdIn(test_file1)) \
        :
            sed.main(['s/$/$/mg'])

            in_lines = fake_out.buffer.getvalue().decode().split('\n')

        self.assertGreater(len(in_lines), 1)
        # This is where this differs from sed because Python re matches $ before AND after newline
        self.assertEqual(in_lines[0], 'this is a file$')
        self.assertEqual(in_lines[1], '$which contains several lines,$')

    def test_delete(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out, \
            patch('sedeuce.sed.sys.stdin', FakeStdIn(test_file1)) \
        :
            sed.main(['3d'])

            out_lines = test_file1.split('\n')
            in_lines = fake_out.buffer.getvalue().decode().split('\n')

        del out_lines[2]
        self.assertEqual(in_lines, out_lines)

    def test_delete_jumps_to_end(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out, \
            patch('sedeuce.sed.sys.stdin', FakeStdIn(test_file1)) \
        :
            # hello appended, then original line deleted
            # appending " world" should not be executed
            sed.main(['3ahello\n3d\n3a\ world'])
            in_lines = fake_out.buffer.getvalue().decode().split('\n')
        self.assertGreater(len(in_lines), 2)
        self.assertEqual(in_lines[2], 'hello')

    def test_branch_to_label(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out, \
            patch('sedeuce.sed.sys.stdin', FakeStdIn(test_file1)) \
        :
            # Should delete 1 line, not 10
            sed.main(['bsomething;1,10d;:something;1d'])

            out_lines = test_file1.split('\n')
            in_lines = fake_out.buffer.getvalue().decode().split('\n')

        del out_lines[0]
        self.assertEqual(in_lines, out_lines)

    def test_append(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out, \
            patch('sedeuce.sed.sys.stdin', FakeStdIn(test_file1)) \
        :
            # Semicolon is not an end command char - only \n is
            sed.main(['9a    this line is appended after line 9;d'])
            out_lines = test_file1.split('\n')
            in_lines = fake_out.buffer.getvalue().decode().split('\n')
        self.assertEqual(len(in_lines), len(out_lines) + 1)
        self.assertEqual(in_lines[8:11], [
            'dsfklaslkdjfa sedf;l asjd',
            'this line is appended after line 9;d',
            'fasjd f ;8675309'
        ])

    def test_append_with_slash(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out, \
            patch('sedeuce.sed.sys.stdin', FakeStdIn(test_file1)) \
        :
            sed.main(['9a\    this line is appended after line 9'])
            out_lines = test_file1.split('\n')
            in_lines = fake_out.buffer.getvalue().decode().split('\n')
        self.assertEqual(len(in_lines), len(out_lines) + 1)
        self.assertEqual(in_lines[8:11], [
            'dsfklaslkdjfa sedf;l asjd',
            '    this line is appended after line 9',
            'fasjd f ;8675309'
        ])

    def test_replace(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out, \
            patch('sedeuce.sed.sys.stdin', FakeStdIn(test_file1)) \
        :
            # Semicolon is not an end command char - only \n is
            sed.main(['10c    this text is put on line 10;d'])
            in_lines = fake_out.buffer.getvalue().decode().split('\n')
        self.assertGreater(len(in_lines), 9)
        self.assertEqual(in_lines[9], 'this text is put on line 10;d')

    def test_replace_with_slash(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out, \
            patch('sedeuce.sed.sys.stdin', FakeStdIn(test_file1)) \
        :
            sed.main(['10c\    this text is put on line 10'])
            in_lines = fake_out.buffer.getvalue().decode().split('\n')
        self.assertGreater(len(in_lines), 9)
        self.assertEqual(in_lines[9], '    this text is put on line 10')

    def test_execute_static_cmd(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out, \
            patch('sedeuce.sed.sys.stdin', FakeStdIn(test_file1)) \
        :
            sed.main(['1,3eecho hello&&echo world'])
            in_lines = fake_out.buffer.getvalue().decode().split('\n')
        if _is_windows():
            # Remove \r characters
            for i in range(len(in_lines)):
                if in_lines[i].endswith('\r'):
                    in_lines[i] = in_lines[i][:-1]
        self.assertEqual(in_lines[:10], [
            'hello',
            'world',
            'this is a file',
            'hello',
            'world',
            'which contains several lines,',
            'hello',
            'world',
            'and I am am am using',
            'it to test'
        ])

    def test_execute_input_pattern(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out, \
            patch('sedeuce.sed.sys.stdin', FakeStdIn('echo a\necho b\necho c')) \
        :
            sed.main(['2e'])
            in_str = fake_out.buffer.getvalue().decode()
        self.assertEqual(in_str, 'echo a\nb\necho c')

    def test_print_filename_stdin(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out, \
            patch('sedeuce.sed.sys.stdin', FakeStdIn('line 1\nline 2\nline3\n')) \
        :
            sed.main(['3F'])
            in_str = fake_out.buffer.getvalue().decode()
        self.assertEqual(in_str, 'line 1\nline 2\n-\nline3\n')

    def test_print_filename(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out:
            sed.main(['3F', 'file1.txt'])
            in_lines = fake_out.buffer.getvalue().decode().split('\n')
        self.assertEqual(in_lines[:5], [
            'this is a file',
            'which contains several lines,',
            'file1.txt',
            'and I am am am using',
            'it to test'
        ])

    def test_set_holdspace(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out:
            sed.main(['1h', 'file1.txt'])
            in_lines = fake_out.buffer.getvalue().decode().split('\n')
        # Nothing should have changed
        self.assertEqual(in_lines[:4], [
            'this is a file',
            'which contains several lines,',
            'and I am am am using',
            'it to test'
        ])

    def test_append_holdspace(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out:
            sed.main(['1H', 'file1.txt'])
            in_lines = fake_out.buffer.getvalue().decode().split('\n')
        # Nothing should have changed
        self.assertEqual(in_lines[:4], [
            'this is a file',
            'which contains several lines,',
            'and I am am am using',
            'it to test'
        ])

    def test_replace_empty_holdspace(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out:
            sed.main(['2g', 'file1.txt'])
            in_lines = fake_out.buffer.getvalue().decode().split('\n')
        self.assertEqual(in_lines[:4], [
            'this is a file',
            '',
            'and I am am am using',
            'it to test'
        ])

    def test_append_empty_holdspace(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out:
            sed.main(['2G', 'file1.txt'])
            in_lines = fake_out.buffer.getvalue().decode().split('\n')
        self.assertEqual(in_lines[:5], [
            'this is a file',
            'which contains several lines,',
            '',
            'and I am am am using',
            'it to test'
        ])

    def test_set_holdspace_and_append(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out:
            sed.main(['1h;2G', 'file1.txt'])
            in_lines = fake_out.buffer.getvalue().decode().split('\n')
        self.assertEqual(in_lines[:5], [
            'this is a file',
            'which contains several lines,',
            'this is a file',
            'and I am am am using',
            'it to test'
        ])

    def test_append_holdspace_and_append(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out:
            sed.main(['1H;2G', 'file1.txt'])
            in_lines = fake_out.buffer.getvalue().decode().split('\n')
        self.assertEqual(in_lines[:6], [
            'this is a file',
            'which contains several lines,',
            '',
            'this is a file',
            'and I am am am using',
            'it to test'
        ])

    def test_set_holdspace_and_set(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out:
            sed.main(['1h;3g', 'file1.txt'])
            in_lines = fake_out.buffer.getvalue().decode().split('\n')
        self.assertEqual(in_lines[:4], [
            'this is a file',
            'which contains several lines,',
            'this is a file',
            'it to test'
        ])

    def test_set_and_append_holdspace_and_set(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out:
            sed.main(['1h;2H;3g', 'file1.txt'])
            in_lines = fake_out.buffer.getvalue().decode().split('\n')
        self.assertEqual(in_lines[:5], [
            'this is a file',
            'which contains several lines,',
            'this is a file',
            'which contains several lines,',
            'it to test'
        ])

    def test_insert(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out, \
            patch('sedeuce.sed.sys.stdin', FakeStdIn(test_file1)) \
        :
            # Semicolon is not an end command char - only \n is
            sed.main(['8i    this line is inserted before line 8;d'])
            out_lines = test_file1.split('\n')
            in_lines = fake_out.buffer.getvalue().decode().split('\n')
        self.assertEqual(len(in_lines), len(out_lines) + 1)
        self.assertEqual(in_lines[6:9], [
            'here is some junk text',
            'this line is inserted before line 8;d',
            'dlkjfkldsjf'
        ])

    def test_insert_with_slash(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out, \
            patch('sedeuce.sed.sys.stdin', FakeStdIn(test_file1)) \
        :
            sed.main(['8i\    this line is inserted before line 8'])
            out_lines = test_file1.split('\n')
            in_lines = fake_out.buffer.getvalue().decode().split('\n')
        self.assertEqual(len(in_lines), len(out_lines) + 1)
        self.assertEqual(in_lines[6:9], [
            'here is some junk text',
            '    this line is inserted before line 8',
            'dlkjfkldsjf'
        ])

    def test_unambiguous_print(self):
        string = (
            ' \t\r\n\v\f\u0020\n\u00A0\n\u1680\u2000\u2001\u2002\u2003\u2004'
            '\u2005\u2006\u2007\u2008\u2009\u200A\u202F\u205F\u3000'
            '\a\b\'\"?hello \\'
        )

        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out, \
            patch('sedeuce.sed.sys.stdin', FakeStdIn(string)) \
        :
            sed.main(['l;d'])
            in_lines = fake_out.buffer.getvalue().decode().split('\n')
        self.assertEqual(in_lines, [
            ' \\t\\r$',
            '\\v\\f $',
            '\\302\\240$',
            '\\341\\232\\200\\342\\200\\200\\342\\200\\201\\342\\200\\202\\342\\200\\203\\342\\200\\',
            '\\204\\342\\200\\205\\342\\200\\206\\342\\200\\207\\342\\200\\210\\342\\200\\211\\342\\',
            '\\200\\212\\342\\200\\257\\342\\201\\237\\343\\200\\200\\a\\b\'"?hello \\\\$'
        ])

    def test_next_command(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out, \
            patch('sedeuce.sed.sys.stdin', FakeStdIn(test_file1)) \
        :
            sed.main(['ahello\nn'])
            in_lines = fake_out.buffer.getvalue().decode().split('\n')
        self.assertEqual(in_lines[:6], [
            'this is a file',
            'hello',
            'which contains several lines,',
            'and I am am am using',
            'hello',
            'it to test'
        ])

    def test_append_next_command(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out:
            sed.main(['3aworld\n3ihello\n3,5N\n3d', 'file1.txt'])
            in_lines = fake_out.buffer.getvalue().decode().split('\n')
        self.assertEqual(in_lines[:6], [
            'this is a file',
            'which contains several lines,',
            'hello',
            'world',
            'and I am am am using',
            'it to test'
        ])

    def test_print_command(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out:
            sed.main(['ablah\n3p', 'file1.txt'])
            in_lines = fake_out.buffer.getvalue().decode().split('\n')
        self.assertEqual(in_lines[:8], [
            'this is a file',
            'blah',
            'which contains several lines,',
            'blah',
            'and I am am am using',
            'and I am am am using',
            'blah',
            'it to test'
        ])

    def test_print_to_newline_command(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out:
            sed.main(['ablah\n3N;4P;4d', 'file1.txt'])
            in_lines = fake_out.buffer.getvalue().decode().split('\n')
        self.assertEqual(in_lines[:8], [
            'this is a file',
            'blah',
            'which contains several lines,',
            'blah',
            'blah',
            'and I am am am using',
            'sed for a while',
            'blah'
        ])

    def test_quit_command(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out:
            rv = sed.main(['aworld\nihello\n3q321', 'file1.txt'])
            in_lines = fake_out.buffer.getvalue().decode().split('\n')
        self.assertEqual(in_lines, [
            'hello',
            'this is a file',
            'world',
            'hello',
            'which contains several lines,',
            'world',
            'hello',
            'and I am am am using',
            'world',
            ''
        ])
        self.assertEqual(rv, 321)

    def test_quit_without_print_command(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out:
            rv = sed.main(['aworld\nihello\n3Q', 'file1.txt'])
            in_lines = fake_out.buffer.getvalue().decode().split('\n')
        self.assertEqual(in_lines, [
            'hello',
            'this is a file',
            'world',
            'hello',
            'which contains several lines,',
            'world',
            'hello',
            ''
        ])
        self.assertEqual(rv, 0)

    def test_append_file_contents(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out:
            sed.main(['ahello\n1r numbers.txt\naworld\n1rnumbers.txt', 'file1.txt'])
            in_lines = fake_out.buffer.getvalue().decode().split('\n')
        self.assertEqual(in_lines[:24], [
            'this is a file',
            'hello',
            '0',
            '1',
            '2',
            '3',
            '4',
            '5',
            '6',
            '7',
            '8',
            '9world',
            '0',
            '1',
            '2',
            '3',
            '4',
            '5',
            '6',
            '7',
            '8',
            '9which contains several lines,',
            'hello',
            'world'
        ])

    def test_append_file_contents_invalid_file(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out:
            # Invalid file should be completely ignored
            sed.main(['r invalid.txt', 'file1.txt'])
            in_lines = fake_out.buffer.getvalue().decode().split('\n')
        self.assertEqual(in_lines[:3], [
            'this is a file',
            'which contains several lines,',
            'and I am am am using'
        ])

    def test_append_lines_from_file(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out:
            # Invalid file should be completely ignored
            sed.main(['R numbers.txt\nahello\nd', 'file1.txt'])
            in_lines = fake_out.buffer.getvalue().decode().split('\n')
        self.assertEqual(in_lines[:6], [
            '0',
            'hello',
            '1',
            'hello',
            '2',
            'hello'
        ])

    def test_test_branch_command(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out:
            # Invalid file should be completely ignored
            sed.main(['s/this/that/;tcat;d;:cat', 'file1.txt'])
            in_lines = fake_out.buffer.getvalue().decode().split('\n')
        self.assertEqual(in_lines, ['that is a file', ''])

    def test_test_branch_not_command(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out:
            # Invalid file should be completely ignored
            sed.main(['s/this/that/;Tcat;d;:cat', 'file1.txt'])
            in_lines = fake_out.buffer.getvalue().decode().split('\n')
        self.assertEqual(in_lines, [
            'which contains several lines,',
            'and I am am am using',
            'it to test',
            'sed for a while',
            '',
            'here is some junk text',
            'dlkjfkldsjf',
            'dsfklaslkdjfa sedf;l asjd',
            'fasjd f ;8675309',
            ';ajsdfj sdljf ajsdfj;sdljf',
            'ajsdfja;sjdf ;sdajf ;l'
        ])

    def test_version_invalid(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out,\
            patch('sedeuce.sed.sys.stderr', new = StringIO()) as fake_err \
        :
            # Invalid file should be completely ignored
            sed.main(['vabc', 'file1.txt'])
            err_dat = fake_err.getvalue()
        self.assertEqual(err_dat, 'sedeuce: Error at expression #1, char 5: Not a valid version number\n')

    def test_version_valid_pass(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out:
            # Invalid file should be completely ignored
            sed.main(['v0.0.1000', 'file1.txt'])
            in_dat = fake_out.buffer.getvalue().decode()
        self.assertEqual(in_dat, test_file1)

    def test_version_valid_fail(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out,\
            patch('sedeuce.sed.sys.stderr', new = StringIO()) as fake_err \
        :
            # Invalid file should be completely ignored
            sed.main(['v10000.0', 'file1.txt'])
            err_dat = fake_err.getvalue()
        self.assertEqual(err_dat, 'sedeuce: Error at expression #1, char 9: expected newer version of sedeuce\n')

    def test_write(self):
        tmp_dir = tempfile.TemporaryDirectory()
        try:
            file_path = os.path.join(tmp_dir.name, 'file.txt')
            with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out, \
                patch('sedeuce.sed.sys.stdin', FakeStdIn(test_file1)) \
            :
                sed.main([f'3,5w {file_path}'])

            with open(file_path, 'r') as fp:
                in_tmp = list(fp.readlines())
            self.assertEqual(in_tmp, [
                'and I am am am using\n',
                'it to test\n',
                'sed for a while\n'
            ])
        finally:
            tmp_dir.cleanup()

    def test_write_up_to_newline(self):
        tmp_dir = tempfile.TemporaryDirectory()
        try:
            file_path = os.path.join(tmp_dir.name, 'file.txt')
            with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out, \
                patch('sedeuce.sed.sys.stdin', FakeStdIn(test_file1)) \
            :
                sed.main([f'3h;4G;4W {file_path}'])

            with open(file_path, 'r') as fp:
                in_tmp = list(fp.readlines())
            self.assertEqual(in_tmp, ['it to test\n'])
        finally:
            tmp_dir.cleanup()

    def test_translate(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out:
            # Invalid file should be completely ignored
            sed.main(['y;\;aeiou;.kbymz;', 'file1.txt'])
            in_lines = fake_out.buffer.getvalue().decode().split('\n')
        self.assertEqual(in_lines, [
            'thys ys k fylb',
            'whych cmntkyns sbvbrkl lynbs,',
            'knd I km km km zsyng',
            'yt tm tbst',
            'sbd fmr k whylb',
            '',
            'hbrb ys smmb jznk tbxt',
            'dlkjfkldsjf',
            'dsfklkslkdjfk sbdf.l ksjd',
            'fksjd f .8675309',
            '.kjsdfj sdljf kjsdfj.sdljf',
            'kjsdfjk.sjdf .sdkjf .l'
        ])

    def test_exchange(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out:
            # Invalid file should be completely ignored
            sed.main(['3h;x', 'file1.txt'])
            in_lines = fake_out.buffer.getvalue().decode().split('\n')
        self.assertEqual(in_lines, [
            '',
            'this is a file',
            'and I am am am using',
            'and I am am am using',
            'it to test',
            'sed for a while',
            '',
            'here is some junk text',
            'dlkjfkldsjf',
            'dsfklaslkdjfa sedf;l asjd',
            'fasjd f ;8675309',
            ';ajsdfj sdljf ajsdfj;sdljf',
            ''
        ])

    def test_zap(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out:
            # Invalid file should be completely ignored
            sed.main(['3,5z', 'file1.txt'])
            in_lines = fake_out.buffer.getvalue().decode().split('\n')
        self.assertEqual(in_lines, [
            'this is a file',
            'which contains several lines,',
            '',
            '',
            '',
            '',
            'here is some junk text',
            'dlkjfkldsjf',
            'dsfklaslkdjfa sedf;l asjd',
            'fasjd f ;8675309',
            ';ajsdfj sdljf ajsdfj;sdljf',
            'ajsdfja;sjdf ;sdajf ;l'
        ])

    def test_line_number(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out:
            # Invalid file should be completely ignored
            sed.main(['5,9=;5z', 'file1.txt'])
            in_lines = fake_out.buffer.getvalue().decode().split('\n')
        self.assertEqual(in_lines, [
            'this is a file',
            'which contains several lines,',
            'and I am am am using',
            'it to test',
            '5',
            '',
            '6',
            '',
            '7',
            'here is some junk text',
            '8',
            'dlkjfkldsjf',
            '9',
            'dsfklaslkdjfa sedf;l asjd',
            'fasjd f ;8675309',
            ';ajsdfj sdljf ajsdfj;sdljf',
            'ajsdfja;sjdf ;sdajf ;l'
        ])

    def test_comment(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out:
            # Invalid file should be completely ignored
            sed.main(['  # this; is a ; comment\nahello', 'file1.txt'])
            in_lines = fake_out.buffer.getvalue().decode().split('\n')
        self.assertEqual(in_lines[:5], [
            'this is a file',
            'hello',
            'which contains several lines,',
            'hello',
            'and I am am am using'
        ])

    def test_set_single_char_commands_failure_extra_chars(self):
        # This should really be a parametrized test, but I'm lazy...
        single_char_commands = 'dDhHgGFlnNpPxz='
        for c in single_char_commands:
            with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out, \
                patch('sedeuce.sed.sys.stderr', new = StringIO()) as fake_err \
            :
                sed.main(['1{}extra'.format(c), 'file1.txt'])
                in_dat = fake_out.buffer.getvalue().decode()
                in_err = fake_err.getvalue()
            self.assertEqual(in_dat, '')
            self.assertEqual(in_err, 'sedeuce: Error at expression #1, char 3: extra characters after command\n')

    def test_escaped_newline(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out:
            sed.main(['ahello\\\nworld', 'file1.txt'])
            in_lines = fake_out.buffer.getvalue().decode().split('\n')
        self.assertEqual(in_lines[:6], [
            'this is a file', 'hello', 'world', 'which contains several lines,', 'hello', 'world'
        ])

    def test_unmatched_close_bracket(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()), \
            patch('sedeuce.sed.sys.stderr', new = StringIO()) as fake_err \
        :
            sed.main(['}ahello', 'file1.txt'])
            err_str = fake_err.getvalue()
        self.assertEqual(err_str, "sedeuce: Error at expression #1, char 1: unexpected `}'\n")

    def test_unmatched_open_bracket(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()), \
            patch('sedeuce.sed.sys.stderr', new = StringIO()) as fake_err \
        :
            sed.main(['{ahello', 'file1.txt'])
            err_str = fake_err.getvalue()
        self.assertEqual(err_str, "sedeuce: Error at expression #1, char 8: unmatched `{'\n")

    def test_bracketed_expression(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out:
            sed.main([
                's/i/o/; 3,5{s/o/u/g;a hello\n/I am/{i whoop\ns/usung/great/;y/I/U/;s/am am am/are/}}',
                'file1.txt'
            ])
            in_lines = fake_out.buffer.getvalue().decode().split('\n')
        self.assertEqual(in_lines, [
            'thos is a file',
            'whoch contains several lines,',
            'whoop',
            'and U are great',
            'hello',
            'ut tu test',
            'hello',
            'sed fur a whule',
            'hello',
            '',
            'here os some junk text',
            'dlkjfkldsjf',
            'dsfklaslkdjfa sedf;l asjd',
            'fasjd f ;8675309',
            ';ajsdfj sdljf ajsdfj;sdljf',
            'ajsdfja;sjdf ;sdajf ;l'
        ])

    def test_quiet(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out:
            sed.main([
                's/i/o/; 3,5ihello\n4,6aworld',
                'file1.txt',
                '-n'
            ])
            in_lines = fake_out.buffer.getvalue().decode().split('\n')
        # Yep, this is expected
        self.assertEqual(in_lines, ['hello', 'hello', 'world', 'hello', 'world', 'world', ''])

    def test_expression_option(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out:
            sed.main([
                'file1.txt',
                '-e', 'a world',
                '--expression', 'y/abc/xyz/',
                '--expression=i hello'
            ])
            in_lines = fake_out.buffer.getvalue().decode().split('\n')
        self.assertEqual(in_lines[:14], [
            'hello',
            'this is x file',
            'world',
            'hello',
            'whizh zontxins severxl lines,',
            'world',
            'hello',
            'xnd I xm xm xm using',
            'world',
            'hello',
            'it to test',
            'world',
            'hello',
            'sed for x while'
        ])

    def test_expressions_from_file(self):
        tmp_dir = tempfile.TemporaryDirectory()
        try:
            file_path = os.path.join(tmp_dir.name, 'file.txt')
            with open(file_path, 'w') as tmp_file:
                tmp_file.write('c blah hi\ns/blah/blah blah/;')
                tmp_file.flush()
            with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out:
                sed.main([
                    '-f', file_path,
                    '--',
                    'file1.txt'
                ])
                in_lines = fake_out.buffer.getvalue().decode().split('\n')
            self.assertEqual(in_lines[:2], ['blah blah hi', 'blah blah hi'])
        finally:
            tmp_dir.cleanup()

    def test_extended_regex(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out, \
            patch('sedeuce.sed.sys.stdin', FakeStdIn(test_file1)) \
        :
            sed.main(['s=.*;([0-9]{3})([0-9]+)=I got your number: \\1-\\2 (I got it)=', '-E'])

            out_lines = test_file1.split('\n')
            in_lines = fake_out.buffer.getvalue().decode().split('\n')

        self.assertEqual(len(in_lines), len(out_lines))
        self.assertEqual(in_lines[9], 'I got your number: 867-5309 (I got it)')

    def test_line_length_option(self):
        string = (
            ' \t\r\n\v\f\u0020\n\u00A0\n\u1680\u2000\u2001\u2002\u2003\u2004'
            '\u2005\u2006\u2007\u2008\u2009\u200A\u202F\u205F\u3000'
            '\a\b\'\"?hello \\'
        )

        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out, \
            patch('sedeuce.sed.sys.stdin', FakeStdIn(string)) \
        :
            sed.main(['l;d', '-l', '35'])
            in_lines = fake_out.buffer.getvalue().decode().split('\n')
        self.assertEqual(in_lines, [
            ' \\t\\r$',
            '\\v\\f $',
            '\\302\\240$',
            '\\341\\232\\200\\342\\200\\200\\342\\200\\',
            '\\201\\342\\200\\202\\342\\200\\203\\342\\',
            '\\200\\204\\342\\200\\205\\342\\200\\206\\',
            '\\342\\200\\207\\342\\200\\210\\342\\200\\',
            '\\211\\342\\200\\212\\342\\200\\257\\342\\',
            '\\201\\237\\343\\200\\200\\a\\b\'"?hello \\',
            '\\\\$'
        ])

    def test_separate_option(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out:
            sed.main(['1,3p;d', 'file1.txt', 'numbers.txt', '-s'])
            in_lines = fake_out.buffer.getvalue().decode().split('\n')
        self.assertEqual(in_lines, [
            'this is a file',
            'which contains several lines,',
            'and I am am am using',
            '0',
            '1',
            '2',
            ''
        ])

    def test_sandbox_option_no_write_pattern(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()),\
            patch('sedeuce.sed.sys.stderr', new = StringIO()) as fake_err \
        :
            # Invalid file should be completely ignored
            sed.main(['w nowrite.txt', 'file1.txt', '--sandbox'])
            err_dat = fake_err.getvalue()
        self.assertEqual(err_dat, 'sedeuce: Error at expression #1, char 1: e/r/w commands disabled in sandbox mode\n')

    def test_sandbox_option_no_write_pattern_to_newline(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()),\
            patch('sedeuce.sed.sys.stderr', new = StringIO()) as fake_err \
        :
            # Invalid file should be completely ignored
            sed.main(['W nowrite.txt', 'file1.txt', '--sandbox'])
            err_dat = fake_err.getvalue()
        self.assertEqual(err_dat, 'sedeuce: Error at expression #1, char 1: e/r/w commands disabled in sandbox mode\n')

    def test_sandbox_option_no_read_pattern(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()),\
            patch('sedeuce.sed.sys.stderr', new = StringIO()) as fake_err \
        :
            # Invalid file should be completely ignored
            sed.main(['r nowrite.txt', 'file1.txt', '--sandbox'])
            err_dat = fake_err.getvalue()
        self.assertEqual(err_dat, 'sedeuce: Error at expression #1, char 1: e/r/w commands disabled in sandbox mode\n')

    def test_sandbox_option_no_read_pattern_to_newline(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()),\
            patch('sedeuce.sed.sys.stderr', new = StringIO()) as fake_err \
        :
            # Invalid file should be completely ignored
            sed.main(['R nowrite.txt', 'file1.txt', '--sandbox'])
            err_dat = fake_err.getvalue()
        self.assertEqual(err_dat, 'sedeuce: Error at expression #1, char 1: e/r/w commands disabled in sandbox mode\n')

    def test_sandbox_option_no_execute(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()),\
            patch('sedeuce.sed.sys.stderr', new = StringIO()) as fake_err \
        :
            # Invalid file should be completely ignored
            sed.main(['e echo hello', 'file1.txt', '--sandbox'])
            err_dat = fake_err.getvalue()
        self.assertEqual(err_dat, 'sedeuce: Error at expression #1, char 1: e/r/w commands disabled in sandbox mode\n')

    def test_sandbox_option_no_substitute_write(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()),\
            patch('sedeuce.sed.sys.stderr', new = StringIO()) as fake_err \
        :
            # Invalid file should be completely ignored
            sed.main(['s/blah/blah/w nowrite.txt', 'file1.txt', '--sandbox'])
            err_dat = fake_err.getvalue()
        self.assertEqual(err_dat, 'sedeuce: Error at expression #1, char 14: e/r/w commands disabled in sandbox mode\n')

    def test_sandbox_option_no_substitute_execute(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()),\
            patch('sedeuce.sed.sys.stderr', new = StringIO()) as fake_err \
        :
            # Invalid file should be completely ignored
            sed.main(['s/blah/blah/e echo hello', 'file1.txt', '--sandbox'])
            err_dat = fake_err.getvalue()
        self.assertEqual(err_dat, 'sedeuce: Error at expression #1, char 14: e/r/w commands disabled in sandbox mode\n')

    def test_end_option(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out:
            # Invalid file should be completely ignored
            sed.main(['a-', 'file1.txt', '--end= '])
            in_lines = fake_out.buffer.getvalue().decode().split('\n')
        self.assertEqual(in_lines, [
            'this - is - a - file',
            'which - contains - several - lines,',
            'and - I - am - am - am - using',
            'it - to - test',
            'sed - for - a - while',
            '',
            'here - is - some - junk - text',
            'dlkjfkldsjf',
            'dsfklaslkdjfa - sedf;l - asjd',
            'fasjd - f - ;8675309',
            ';ajsdfj - sdljf - ajsdfj;sdljf',
            'ajsdfja;sjdf - ;sdajf - ;l- '
        ])

    def test_in_place_option(self):
        tmp_dir = tempfile.TemporaryDirectory()
        try:
            file_path = os.path.join(tmp_dir.name, 'file.txt')
            with open(file_path, 'w') as fd:
                fd.write(test_file1)
            with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out:
                sed.main(['3p;d', file_path, '-i'])
                out_dat = fake_out.buffer.getvalue().decode()
            self.assertEqual(out_dat, '')
            with open(file_path, 'r') as fd:
                file_dat = fd.read()
            self.assertEqual(file_dat, 'and I am am am using\n')
        finally:
            tmp_dir.cleanup()

    def test_in_place_backup_option(self):
        tmp_dir = tempfile.TemporaryDirectory()
        try:
            file_path = os.path.join(tmp_dir.name, 'file.txt')
            with open(file_path, 'w') as fd:
                fd.write(test_file1)
            with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out:
                sed.main(['3p;d', file_path, '-i', '.bak'])
                out_dat = fake_out.buffer.getvalue().decode()
            self.assertEqual(out_dat, '')
            with open(file_path, 'r') as fd:
                file_dat = fd.read()
            with open(file_path + '.bak', 'r') as fd:
                bak_file_dat = fd.read()
            self.assertEqual(bak_file_dat, test_file1)
            self.assertEqual(file_dat, 'and I am am am using\n')
        finally:
            tmp_dir.cleanup()


if __name__ == '__main__':
    unittest.main()
