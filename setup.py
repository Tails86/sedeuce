import setuptools
import subprocess

# This project is only packaged as sdist so that this setup.py script runs at the target

with open('README.md', 'r', encoding='utf-8') as fh:
    long_description = fh.read()

def _is_sed_found():
    try:
        try:
            cmd = ['sed', '--version']
            sed_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except FileNotFoundError:
            # This happens if sed is not installed
            return False

        try:
            out, _ = sed_proc.communicate(timeout=10.0)
        except subprocess.TimeoutExpired:
            # Something went wrong with this execution - assume invalid sed installation
            return False

        # Ensure this actually returned a sed version string and isn't just a past installation of sedeuce
        return (b'sed' in out and b'sedeuce' not in out)
    except Exception:
        # Covering all bases - assume invalid sed installation
        return False

# Always have sedeuce as script
console_scripts = ['sedeuce=sedeuce.__main__:main']

# This isn't perfect, but it's better than nothing
# Install sed alias script only if sed is not already found on the system
if not _is_sed_found():
    print('Installing sed script because sed not found on system')
    console_scripts.append('sed=sedeuce.__main__:main')
else:
    print('Not installing sed; sed already found on system')

setuptools.setup(
    name='sedeuce',
    author='James Smith',
    author_email='jmsmith86@gmail.com',
    description='A sed clone in Python with both CLI and library interfaces',
    keywords='sed, files, regex, replace',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/Tails86/sedeuce',
    project_urls={
        'Documentation': 'https://github.com/Tails86/sedeuce',
        'Bug Reports': 'https://github.com/Tails86/sedeuce/issues',
        'Source Code': 'https://github.com/Tails86/sedeuce'
    },
    package_dir={'': 'src'},
    packages=setuptools.find_packages(where='src'),
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: Console',
        'Intended Audience :: Information Technology',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3 :: Only',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.6',
    extras_require={
        'dev': ['check-manifest']
    },
    entry_points={
        'console_scripts': console_scripts
    }
)