import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="k8swatcher",
    version="__VERSION_HERE__",
    author="bitsofinfo",
    author_email="bitsofinfo.g@gmail.com",
    description="Library for watching kubernetes events",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/bitsofinfo/k8swatcher",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    install_requires=[
        'kubernetes>=23.3.0',
        'typer>=0.4.1',
        'pydantic>=1.9.0'
    ],
    entry_points = {
        "console_scripts": ['k8swatcher = k8swatcher.cli:main']
    },
    python_requires='>=3.9',
)
