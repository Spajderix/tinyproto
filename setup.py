import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="tinyproto",
    version="2.0.1",
    author="Spajderix",
    author_email="spajderix@gmail.com",
    description="Small tcp protocol library",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Spajderix/tinyproto",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU Lesser General Public License v3 or later (LGPLv3+)",
        "Operating System :: OS Independent",
    ],
)
