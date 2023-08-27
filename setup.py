import setuptools

with open('README.md', 'r', encoding='utf-8') as fh:
    long_description = fh.read()

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
        'Development Status :: 2 - Pre-Alpha',
        'Environment :: Console',
        'Intended Audience :: Information Technology',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3 :: Only',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.5',
    extras_require={
        'dev': ['check-manifest']
    },
    entry_points={
        'console_scripts': ['sed=sedeuce.__main__:main', 'sedeuce=sedeuce.__main__:main']
    }
)