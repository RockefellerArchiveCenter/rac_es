from datetime import datetime

import elasticsearch_dsl as es
from elasticsearch.helpers import streaming_bulk

from .analyzers import base_analyzer


class ResolveException(Exception):
    pass


class DateField(es.Date):
    """Custom Date field to support indexing dates without timezones."""

    def deserialize(self, data):
        """Properly deserializes date fields.

        :returns: date data
        :rtype: date
        """
        data = super(DateField, self).deserialize(data)
        if isinstance(data, datetime):
            data = data.date()
        return data


class Date(es.InnerDoc):
    """Refers to a single date or date range.

    Used on Documents to create human and machine readable date representations.
    The `expression` field is intended to be a human readable representation of
    a date or date range, while the begin and end values are machine readable
    and actionable values.
    """
    begin = DateField()
    end = DateField()
    expression = es.Text(required=True)
    label = es.Text(required=True)
    type = es.Text(required=True)


class ExternalIdentifier(es.InnerDoc):
    """Abstract representation of external identifier object.

    Used on Documents to unambiguously tie them to source data.
    """
    identifier = es.Text(required=True)
    source = es.Text(required=True)
    source_identifier = es.Text()


class Extent(es.InnerDoc):
    """The size of a group of records."""
    type = es.Text(required=True)
    value = es.Text(required=True)


class Language(es.InnerDoc):
    """A human language."""
    expression = es.Text(required=True)
    identifier = es.Text(required=True)


class Subnote(es.InnerDoc):
    """Abstract wrapper for note content, associated with Note Documents."""
    content = es.Text(required=True, analyzer=base_analyzer)
    type = es.Text(required=True)


class Note(es.InnerDoc):
    """Abstract representation of notes, which are typed and contain human
    readable content in a Subnotes InnerDoc."""
    source = es.Text(required=True)
    subnotes = es.Object(Subnote, required=True)
    title = es.Text(
        required=True,
        analyzer=base_analyzer,
        fields={
            'keyword': es.Keyword()})
    type = es.Text(required=True)


class Reference(es.InnerDoc):
    """An embedded reference to another object."""
    title = es.Text(
        required=True,
        analyzer=base_analyzer,
        fields={
            'keyword': es.Keyword()})
    type = es.Text(required=True)
    external_identifiers = es.Nested(ExternalIdentifier)
    identifier = es.Text(required=True)
    order = es.Integer()
    level = es.Text()
    relator = es.Text()
    role = es.Text()


class RightsGranted(es.InnerDoc):
    """Abstract wrapper for RightsGranted information, associated with a
    RightsStatement Document."""
    act = es.Text(required=True)
    begin = DateField(required=True)
    end = DateField(required=True)
    notes = es.Nested(Note)
    restriction = es.Text(required=True)


class RightsStatement(es.InnerDoc):
    """Machine readable representation of restrictions or permissions,
    generally related to a group of archival records.

    This structure is based
    on the PREservation Metadata: Implementation Strategies (PREMIS) Rights entity.
    """
    begin = DateField(required=True)
    copyright_status = es.Text()
    determination_date = DateField(required=True)
    end = DateField(required=True)
    jurisdiction = es.Text()
    notes = es.Nested(Note)
    other_basis = es.Text()
    rights_granted = es.Nested(RightsGranted, required=True)
    rights_type = es.Text(required=True)
    type = es.Text(required=True)


class BaseDescriptionComponent(es.Document):
    """Base class for DescriptionComponents and Reference objects with
    common fields."""

    external_identifiers = es.Object(ExternalIdentifier, required=True)
    title = es.Text(
        required=True,
        analyzer=base_analyzer,
        fields={
            'keyword': es.Keyword()})
    type = es.Text(required=True, fields={'keyword': es.Keyword()})
    uri = es.Keyword(required=True)

    @classmethod
    def _matches(cls, hit):
        """Ensures that this class is never used for deserialization."""
        return False

    def add_source_identifier_fields(self):
        """Adds source_identifier fields to BaseDescriptionComponents.

        source_identifier fields are a concatenation of the source and identifier,
        creating a unique identifier that can be searched.
        """
        for e in self.external_identifiers:
            e.source_identifier = "{}_{}".format(e.source, e.identifier)
        try:
            for relation in self.relations_in_self:
                for obj in getattr(self, relation):
                    for e in obj.external_identifiers:
                        e.source_identifier = "{}_{}".format(
                            e.source, e.identifier)
        except AttributeError:
            pass

    class Index:
        name = 'default'

    def prepare_streaming_dict(self, identifier, op_type="index"):
        """Prepares DescriptionComponent for bulk indexing.

        Executes custom save methods which would not otherwise be called when
        data is passed to a bulk method.

        :returns: an object ready to be indexed.
        :rtype: dict
        """
        self.meta.id = identifier
        self.add_source_identifier_fields()
        doc = self.to_dict(True)
        doc["_op_type"] = op_type
        return doc

    @classmethod
    def bulk_action(self, connection, actions, max_objects=None):
        """Performs a bulk action on a list of objects.

        This method is strongly preferred over the atomic `save` method, because
        it provides better performance.

        :returns: Elasticsearch identifiers of all indexed objects
        :rtype: list
        """
        indexed = []
        indexed_count = 0
        for ok, result in streaming_bulk(connection, actions, refresh=True):
            action, result = result.popitem()
            if not ok:
                raise Exception(
                    "Failed to {} document {}: {}".format(action, result["_id"], result))
            else:
                indexed.append(result["_id"])
                indexed_count += 1
            if max_objects and indexed_count == max_objects:
                break
        return indexed

    def save(self, **kwargs):
        """Adds custom save behaviors for BaseDescriptionComponents."""
        self.add_source_identifier_fields()
        return super(BaseDescriptionComponent, self).save(
            refresh=True, **kwargs)


class Agent(BaseDescriptionComponent):
    """A person, organization or family that was involved in the creation and
    maintenance of records, or is the subject of those records."""
    description = es.Text(
        analyzer=base_analyzer, fields={
            'keyword': es.Keyword()})
    dates = es.Object(Date)
    notes = es.Nested(Note)

    @classmethod
    def search(cls, **kwargs):
        """Provides custom filtering for searches."""
        search = super(Agent, cls).search(**kwargs)
        return search.filter('term', type='agent')


class Collection(BaseDescriptionComponent):
    """A group of archival records which contains other groups of records,
    and may itself be part of a larger Collection.

    Collections are not physical groups of records, such as boxes and folders,
    but are intellectually significant aggregations which are crucial to
    understanding the context of records creation and maintenance, such as
    record groups or series.
    """
    dates = es.Object(Date, required=True)
    extents = es.Nested(Extent, required=True)
    languages = es.Object(Language, required=True)
    level = es.Text(fields={'keyword': es.Keyword()})
    notes = es.Nested(Note)
    rights_statements = es.Nested(RightsStatement)
    agents = es.Nested(Reference)
    ancestors = es.Nested(Reference)
    children = es.Nested(Reference)
    creators = es.Nested(Reference)
    terms = es.Nested(Reference)

    @classmethod
    def search(cls, **kwargs):
        """Provides custom filtering for searches."""
        search = super(Collection, cls).search(**kwargs)
        return search.filter('term', type='collection')


class Object(BaseDescriptionComponent):
    """A group of archival records which is part of a larger Collection, but
    does not contain any other aggregations."""
    dates = es.Object(Date, required=True)
    languages = es.Object(Language)
    extents = es.Nested(Extent)
    notes = es.Nested(Note)
    rights_statements = es.Nested(RightsStatement)
    agents = es.Nested(Reference)
    ancestors = es.Nested(Reference)
    terms = es.Nested(Reference)

    @classmethod
    def search(cls, **kwargs):
        """Provides custom filtering for searches."""
        search = super(Object, cls).search(**kwargs)
        return search.filter('term', type='object')


class Term(BaseDescriptionComponent):
    """A subject, geographic area, document format or other controlled term."""

    @classmethod
    def search(cls, **kwargs):
        """Provides custom filtering for searches."""
        search = super(Term, cls).search(**kwargs)
        return search.filter('term', type='term')
