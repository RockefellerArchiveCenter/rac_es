# rac_es

Helpers for Elasticsearch, including Analyzers and Documents.

[![Build Status](https://travis-ci.org/RockefellerArchiveCenter/rac_es.svg?branch=base)](https://travis-ci.org/RockefellerArchiveCenter/rac_es)

## Setup

Make sure this library is installed:

    $ pip install rac_es


## Usage

You can then use `rac_es` in your Python code by importing it:

    import rac_es


## What's Here

### Analyzers

rac_es includes analyzers which provide custom processing of text fields.

### Documents

The Elasticsearch Document definitions in rac_es match the four main object
types in the RAC data model: Agents, Collections, Objects and Terms. In addition
to these definitions, rac_es provides custom search and save methods for these
Documents, including bulk save and delete methods.

## Development
This repository contains a configuration file for git [pre-commit](https://pre-commit.com/) hooks which help ensure that code is linted before it is checked into version control. It is strongly recommended that you install these hooks locally by installing pre-commit and running `pre-commit install`.

## License

This code is released under an [MIT License](LICENSE).
