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
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out, \
            patch('sedeuce.sed.sys.stdin', FakeStdIn(test_file1)) \
        :
            # TODO: This may be problematic if trying to execute in Windows? - test that
            tmp = tempfile.NamedTemporaryFile('r')
            sed.main([f'3s/am/sam;/w {tmp.name}'])

            in_tmp = list(tmp.readlines())

        self.assertEqual(len(in_tmp), 1)
        self.assertEqual(in_tmp[0], 'and I sam; am am using\n')

    def test_substitute_number_plus_execute(self):
        with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out, \
            patch('sedeuce.sed.sys.stdin', FakeStdIn('xyz\n9876 1234\nabcd')) \
        :
            # This finds 1234 and executes "echo $((43 * 21))" for that match
            sed.main(['s=\\([0-9]\\)\\([0-9]\\)\\([0-9]\\)\\([0-9]\\)=echo $((\\4\\3 * \\2\\1))=2e'])

            in_lines = fake_out.buffer.getvalue().decode().split('\n')

        self.assertEqual(len(in_lines), 3)
        self.assertEqual(in_lines[1], '9876 903')

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
            sed.main(['1,3eecho hello;echo world'])
            in_lines = fake_out.buffer.getvalue().decode().split('\n')
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
            '\\341\\232\\200\\342\\200\\200\\342\\200\\201\\342\\200\\202\\342\\200\\203\\342\\200'
            '\\204\\342\\200\\205\\342\\200\\206\\342\\200\\207\\342\\200\\210\\342\\200\\211\\342'
            '\\200\\212\\342\\200\\257\\342\\201\\237\\343\\200\\200\\a\\b\'"?hello \\\\$'
        ])






    def test_set_single_char_commands_failure_extra_chars(self):
        # This should really be a parametrized test, but I'm lazy...
        single_char_commands = 'dDhHgGFl'
        for c in single_char_commands:
            with patch('sedeuce.sed.sys.stdout', new = FakeStdOut()) as fake_out, \
                patch('sedeuce.sed.sys.stderr', new = StringIO()) as fake_err \
            :
                sed.main(['1{}extra'.format(c), 'file1.txt'])
                in_dat = fake_out.buffer.getvalue().decode()
                in_err = fake_err.getvalue()
            self.assertEqual(in_dat, '')
            self.assertEqual(in_err, 'sedeuce: Error at expression #1, char 3: extra characters after command\n')

if __name__ == '__main__':
    unittest.main()