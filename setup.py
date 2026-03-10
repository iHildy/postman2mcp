# setup.py
from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="postman2mcp",
    version="0.1.0",
    author="Géraldine Geoffroy",
    author_email="grldn.geoffroy@gmail.com",
    description="CLI tool to convert Postman collections to MCP-compatible FastAPI projects.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/gegedenice/postman2mcp",
    packages=find_packages(),
    install_requires=[
        "click",
        "requests"
    ],
    python_requires=">=3.7",
    include_package_data=True,
    entry_points={
        "console_scripts": [
            "postman2mcp=postman2mcp.cli:main",
            "postman2openapi=postman2mcp.cli:openapi_main",
        ]
    },
    license="MIT",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
