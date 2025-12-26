from setuptools import find_packages, setup

setup(
    name="quantvn",
    version="0.1.6",
    packages=find_packages(),
    install_requires=[
        "requests",
        "pandas",
        "matplotlib",
        "tqdm",
        "ta"
    ],
    author="quantvn",
    description="QuantVN API Library for Financial Data Analysis",
    # long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
    ],
    python_requires=">=3.9",
)
