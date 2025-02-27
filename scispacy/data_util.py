
from typing import NamedTuple, List, Iterator, Dict, Tuple
import tarfile
import atexit
import os
import shutil
import tempfile

from scispacy.file_cache import cached_path

class MedMentionEntity(NamedTuple):
    start: int
    end: int
    mention_text: str
    mention_type: str
    umls_id: str

class MedMentionExample(NamedTuple):
    title: str
    abstract: str
    text: str
    pubmed_id: str
    entities: List[MedMentionEntity]


def process_example(lines: List[str]) -> MedMentionExample:
    """
    Processes the text lines of a file corresponding to a single MedMention abstract,
    extracts the title, abstract, pubmed id and entities. The lines of the file should
    have the following format:
    PMID | t | Title text
    PMID | a | Abstract text
    PMID TAB StartIndex TAB EndIndex TAB MentionTextSegment TAB SemanticTypeID TAB EntityID
    ...
    """
    pubmed_id, _, title = [x.strip() for x in lines[0].split("|", maxsplit=2)]
    _, _, abstract = [x.strip() for x in lines[1].split("|", maxsplit=2)]

    entities = []
    for entity_line in lines[2:]:
        _, start, end, mention, mention_type, umls_id = entity_line.split("\t")
        mention_type = mention_type.split(",")[0]
        entities.append(MedMentionEntity(int(start), int(end),
                                         mention, mention_type, umls_id))
    return MedMentionExample(title, abstract, title + " " + abstract, pubmed_id, entities)

def med_mentions_example_iterator(filename: str) -> Iterator[MedMentionExample]:
    """
    Iterates over a Med Mentions file, yielding examples.
    """
    with open(filename, "r") as med_mentions_file:
        lines = []
        for line in med_mentions_file:
            line = line.strip()
            if line:
                lines.append(line)
            else:
                yield process_example(lines)
                lines = []
        # Pick up stragglers
        if lines:
            yield process_example(lines)

def read_med_mentions(filename: str):
    """
    Reads in the MedMentions dataset into Spacy's
    NER format.
    """
    examples = []
    for example in med_mentions_example_iterator(filename):
        spacy_format_entities = [(x.start, x.end, x.mention_type) for x in example.entities]
        examples.append((example.text, {"entities": spacy_format_entities}))

    return examples


def read_full_med_mentions(directory_path: str,
                           label_mapping: Dict[str, str] = None,
                           span_only: bool = False,
                           spacy_format: bool = True):

    def _cleanup_dir(dir_path: str):
        if os.path.exists(dir_path):
            shutil.rmtree(dir_path)

    resolved_directory_path = cached_path(directory_path)
    if "tar.gz" in directory_path:
        # Extract dataset to temp dir
        tempdir = tempfile.mkdtemp()
        print(f"extracting dataset directory {resolved_directory_path} to temp dir {tempdir}")
        with tarfile.open(resolved_directory_path, 'r:gz') as archive:
            archive.extractall(tempdir)
        # Postpone cleanup until exit in case the unarchived
        # contents are needed outside this function.
        atexit.register(_cleanup_dir, tempdir)

        resolved_directory_path = tempdir


    expected_names = ["corpus_pubtator.txt",
                      "corpus_pubtator_pmids_all.txt",
                      "corpus_pubtator_pmids_dev.txt",
                      "corpus_pubtator_pmids_test.txt",
                      "corpus_pubtator_pmids_trng.txt"]

    corpus = os.path.join(resolved_directory_path, expected_names[0])
    examples = med_mentions_example_iterator(corpus)

    train_ids = {x.strip() for x in open(os.path.join(resolved_directory_path, expected_names[4]))}
    dev_ids = {x.strip() for x in open(os.path.join(resolved_directory_path, expected_names[2]))}
    test_ids = {x.strip() for x in open(os.path.join(resolved_directory_path, expected_names[3]))}

    train_examples = []
    dev_examples = []
    test_examples = []

    def label_function(label):
        if span_only:
            return "ENTITY"
        if label_mapping is None:
            return label
        else:
            return label_mapping[label]

    for example in examples:
        spacy_format_entities = [(x.start, x.end, label_function(x.mention_type)) for x in example.entities]
        spacy_example = (example.text, {"entities": spacy_format_entities})
        if example.pubmed_id in train_ids:
            train_examples.append(spacy_example if spacy_format else example)

        elif example.pubmed_id in dev_ids:
            dev_examples.append(spacy_example if spacy_format else example)

        elif example.pubmed_id in test_ids:
            test_examples.append(spacy_example if spacy_format else example)

    return train_examples, dev_examples, test_examples


SpacyNerExample = Tuple[str, Dict[str, List[Tuple[int, int, str]]]] # pylint: disable=invalid-name

def _handle_sentence(examples: List[Tuple[str, str]]) -> SpacyNerExample:
    """
    Processes a single sentence by building it up as a space separated string
    with its corresponding typed entity spans.
    """
    start_index = -1
    current_index = 0
    in_entity = False
    entity_type: str = ""
    sent = ""
    entities: List[Tuple[int, int, str]] = []
    for word, entity in examples:
        sent += word
        sent += " "
        if entity != 'O':
            if in_entity:
                pass
            else:
                start_index = current_index
                in_entity = True
                entity_type = entity[2:].upper()
        else:
            if in_entity:
                end_index = current_index - 1
                entities.append((start_index, end_index, entity_type))
            in_entity = False
            entity_type = ""
            start_index = -1
        current_index += (len(word) + 1)
    if in_entity:
        end_index = current_index - 1
        entities.append((start_index, end_index, entity_type))

    # Remove last space.
    sent = sent[:-1]
    return (sent, {'entities': entities})


def read_ner_from_tsv(filename: str) -> List[SpacyNerExample]:
    """
    Reads BIO formatted NER data from a TSV file, such as the
    NER data found here:
    https://github.com/cambridgeltl/MTL-Bioinformatics-2016

    Data is expected to be 2 tab seperated tokens per line, with
    sentences denoted by empty lines. Sentences read by this
    function will be already tokenized, but returned as a string,
    as this is the format required by SpaCy. Consider using the
    WhitespaceTokenizer(scispacy/util.py) to split this data
    with a SpaCy model.

    Parameters
    ----------
    filename : str
        The path to the tsv data.

    Returns
    -------
    spacy_format_data : List[SpacyNerExample]
        The BIO tagged NER examples.
    """
    spacy_format_data = []
    examples: List[Tuple[str, str]] = []
    for line in open(cached_path(filename)):
        line = line.strip()
        if line.startswith('-DOCSTART-'):
            continue
        # We have reached the end of a sentence.
        if not line:
            if not examples:
                continue
            spacy_format_data.append(_handle_sentence(examples))
            examples = []
        else:
            word, entity = line.split("\t")
            examples.append((word, entity))
    if examples:
        spacy_format_data.append(_handle_sentence(examples))

    return spacy_format_data
