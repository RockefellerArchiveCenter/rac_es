from datetime import datetime

import elasticsearch_dsl as es
import shortuuid

from .analyzers import base_analyzer


class ResolveException(Exception):
    pass


class DateField(es.Date):
    """
    Custom Date field to support indexing dates without timezones.
    """

    def deserialize(self, data):
        data = super(DateField, self).deserialize(data)
        if isinstance(data, datetime):
            data = data.date()
        return data


class Date(es.InnerDoc):
    """
    Refers to a single date or date range.
    Used on Documents to create human and machine readable date representations.
    The `expression` field is intended to be a human readable representation of a date or date range,
    while the begin and end values are machine readable and actionable values.
    """
    begin = DateField(required=True)
    end = DateField()
    expression = es.Text(required=True)
    label = es.Text(required=True)
    type = es.Text(required=True)


class ExternalIdentifier(es.InnerDoc):
    """
    Abstract representation of external identifier object.
    Used on Documents to unambiguously tie them to source data.
    """
    identifier = es.Text(required=True)
    source = es.Text(required=True)
    source_identifier = es.Text()


class Extent(es.InnerDoc):
    """
    The size of a group of records.
    """
    type = es.Text(required=True)
    value = es.Float(required=True)


class Language(es.InnerDoc):
    """
    A human language.
    """
    expression = es.Text(required=True)
    identifier = es.Text(required=True)


class Subnote(es.InnerDoc):
    """
    Abstract wrapper for note content, associated with Note Documents.
    """
    content = es.Text(required=True, analyzer=base_analyzer)
    type = es.Text(required=True)


class Note(es.InnerDoc):
    """
    Abstract representation of notes, which are typed and contain human readable
    content in a Subnotes InnerDoc.
    """
    source = es.Text(required=True)
    subnotes = es.Object(Subnote, required=True)
    title = es.Text(
        required=True,
        analyzer=base_analyzer,
        fields={
            'keyword': es.Keyword()})
    type = es.Text(required=True)


class RightsGranted(es.InnerDoc):
    """
    Abstract wrapper for RightsGranted information, associated with a RightsStatement Document.
    """
    act = es.Text(required=True)
    begin = DateField(required=True)
    end = DateField(required=True)
    notes = es.Nested(Note)
    restriction = es.Text(required=True)


class RightsStatement(es.InnerDoc):
    """
    Machine readable representation of restrictions or permissions,
    generally related to a group of archival records. This structure is based
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
    """
    Base class for DescriptionComponents and Reference objects with
    common fields.
    """

    component_reference = es.Join(relations={'component': 'reference'})
    external_identifiers = es.Object(ExternalIdentifier, required=True)
    id = es.Text(required=True)
    title = es.Text(
        required=True,
        analyzer=base_analyzer,
        fields={
            'keyword': es.Keyword()})
    type = es.Text(required=True, fields={'keyword': es.Keyword()})

    @classmethod
    def _matches(cls, hit):
        """
        Ensures that this class is never used for deserialization.
        """
        return False

    def add_source_identifier_fields(self):
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

    def save(self, **kwargs):
        """
        Create source_identifier field as a concatenation of external
        identifier source and identifier.
        """
        self.add_source_identifier_fields()
        return super(BaseDescriptionComponent, self).save(
            refresh=True, **kwargs)

    class Index:
        name = 'default'


class DescriptionComponent(BaseDescriptionComponent):
    """
    Wrapper for actual description elements.
    """
    @classmethod
    def _matches(cls, hit):
        """Ensure we only get components back."""
        return hit['_source']['component_reference'] == 'component'

    @classmethod
    def search(cls, **kwargs):
        return cls._index.search(
            **kwargs).filter('term', component_reference='component')

    def generate_id(self):
        return shortuuid.uuid()

    def save_reference(self, index, identifier, resolved_obj, relation):
        reference = Reference(
            _routing=self.meta.id,
            _index=index,
            _id=identifier,
            component_reference={'name': 'reference', 'parent': self.meta.id},
            id=identifier,
            relation=relation,
            uri='/{}/{}'.format(index, resolved_obj.meta.id),
            type=resolved_obj.type,
            title=resolved_obj.title,
            external_identifiers=resolved_obj.external_identifiers
        )
        reference.save()
        return reference

    def add_references(self, source_identifier, resolved_obj, relation):
        """
        Indexes child reference to this object. This allows for the edge case
        where one object has multiple relations to the same object. Likely this
        would be a data quality issue (for example a term associated with the
        same object multiple times), but given the state of our data, it's probably
        best to account for this.
        """
        new_references = []
        index = self.meta.index if (
            'index' in self.meta) else self._index._name
        references = self.get_references(
            source_identifier=source_identifier,
            relation=relation)
        if len(references) > 0:
            for reference in references:
                new = self.save_reference(
                    index, reference.meta.id, resolved_obj, relation)
                new_references.append(new)
        else:
            new = self.save_reference(
                index, self.generate_id(), resolved_obj, relation)
            new_references.append(new)
        return new_references

    def search_references(self, **kwargs):
        s = Reference.search()
        s = s.filter('parent_id', type='reference', id=self.meta.id)
        if kwargs.get('source_identifier'):
            s = s.filter(
                'match_phrase',
                external_identifiers__source_identifier=kwargs.get('source_identifier'))
        if kwargs.get('relation'):
            s = s.filter('match_phrase', relation=kwargs.get('relation'))
        return s.params(routing=self.meta.id)

    def get_references(self, **kwargs):
        """Get references from inner_hits already present or by searching."""
        if 'inner_hits' in self.meta and 'reference' in self.meta.inner_hits:
            return self.meta.inner_hits.reference.hits
        return list(self.search_references(**kwargs))

    def resolve_relations_to_self(self):
        """
        Finds references in other Documents to this Document and creates or
        updates a child Reference Document for each. These relations are listed
        as strings which correspond to a key in a `relations_to_self` attribute
        on the main Document object.
        """
        try:
            self_ids = ["{}_{}".format(i.source, i.identifier)
                        for i in self.external_identifiers]
            for relation in self.relations_to_self:
                relation_key = "{}__external_identifiers__source_identifier".format(
                    relation)
                for i in self_ids:
                    parents = DescriptionComponent.search().filter(
                        'match_phrase', **{relation_key: i}).execute()
                    for p in parents:
                        p.add_references(i, self, relation)
        except AttributeError:
            pass

    def resolve_relations_in_self(self):
        """
        Iterates through each key in this Document which contains references to
        other Documents, and creates or updates a Reference Document for each.
        These relations are listed as strings which correspond to a key in a
        `relations_in_self` attribute on the main Document object.
        """
        try:
            for relation in self.relations_in_self:
                # Nested list comprehension, what's up?!?!
                parent_ids = ["{}_{}".format(i.source, i.identifier)
                              for obj in getattr(self, relation)
                              for i in obj.external_identifiers]
                for i in parent_ids:
                    source_objs = DescriptionComponent.search().filter(
                        'match_phrase', external_identifiers__source_identifier=i).execute()
                    for o in source_objs:
                        self.add_references(i, o, relation)
        except AttributeError:
            pass

    def prepare_streaming_dict(self, identifier):
        """
        Executes custom save methods which would not otherwise be called when
        data is passed to a bulk method. Returns a dict which can be indexed.
        """
        self.meta.id = identifier
        self.component_reference = "component"
        self.resolve_relations_in_self()
        self.resolve_relations_to_self()
        self.add_source_identifier_fields()
        yield self.to_dict(True)

    def save(self, **kwargs):
        """
        Overrides save to resolve relations.
        """
        self.resolve_relations_in_self()
        self.resolve_relations_to_self()
        self.component_reference = 'component'
        return super(DescriptionComponent, self).save(**kwargs)


class Reference(BaseDescriptionComponent):
    """
    A minimal reference to a Document.
    """
    uri = es.Text()
    order = es.Integer()
    relation = es.Text()

    @classmethod
    def _matches(cls, hit):
        """
        Use Reference class for child documents with child name 'reference'.
        """
        return isinstance(hit['_source']['component_reference'], dict) \
            and hit['_source']['component_reference'].get('name') == 'reference'

    @classmethod
    def search(cls, **kwargs):
        return cls._index.search(
            **kwargs).exclude('term', component_reference='component')

    def save(self, **kwargs):
        self.meta.routing = self.component_reference.parent
        return super(Reference, self).save(**kwargs)


class Agent(DescriptionComponent):
    """
    A person, organization or family that was involved in the creation and
    maintenance of records, or is the subject of those records.
    """
    description = es.Text(
        analyzer=base_analyzer, fields={
            'keyword': es.Keyword()})
    dates = es.Object(Date)
    notes = es.Nested(Note)

    relations_to_self = ('agents', 'creators',)

    @classmethod
    def search(cls, **kwargs):
        search = super(Agent, cls).search(**kwargs)
        return search.filter('term', type='agent')


class Collection(DescriptionComponent):
    """
    A group of archival records which contains other groups of records,
    and may itself be part of a larger Collection.  Collections are not
    physical groups of records, such as boxes and folders, but are intellectually
    significant aggregations which are crucial to understanding the context of
    records creation and maintenance, such as record groups or series.
    """
    dates = es.Object(Date, required=True)
    extents = es.Nested(Extent, required=True)
    languages = es.Object(Language, required=True)
    level = es.Text(fields={'keyword': es.Keyword()})
    notes = es.Nested(Note)
    rights_statements = es.Nested(RightsStatement)

    relations_to_self = ('ancestors', 'children', 'collections',)
    relations_in_self = (
        'agents',
        'ancestors',
        'children',
        'creators',
        'terms',
    )

    @classmethod
    def search(cls, **kwargs):
        search = super(Collection, cls).search(**kwargs)
        return search.filter('term', type='collection')


class Object(DescriptionComponent):
    """
    A group of archival records which is part of a larger Collection,
    but does not contain any other aggregations.
    """
    dates = es.Object(Date, required=True)
    languages = es.Object(Language)
    extents = es.Nested(Extent, required=True)
    notes = es.Nested(Note)
    rights_statements = es.Nested(RightsStatement)

    relations_to_self = ('ancestors', 'children', 'objects',)
    relations_in_self = ('agents', 'ancestors', 'terms')

    @classmethod
    def search(cls, **kwargs):
        search = super(Object, cls).search(**kwargs)
        return search.filter('term', type='object')


class Term(DescriptionComponent):
    """
    A subject, geographic area, document format or other controlled term.
    """

    relations_to_self = ('terms',)

    @classmethod
    def search(cls, **kwargs):
        search = super(Term, cls).search(**kwargs)
        return search.filter('term', type='term')
