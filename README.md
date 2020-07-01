# rac_es

Helpers for Elasticsearch, including Analyzers and Documents.

## Setup

Make sure this library is installed:

    $ pip install git+git://github.com/RockefellerArchiveCenter/rac_es.git


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


## License

This code is released under an [MIT License](LICENSE).
