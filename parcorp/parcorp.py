import argparse
import collections
import itertools
import logging
import os
import time
from typing import List

import lxml.etree
import sqlite3


LOGGER = logging.getLogger()


def filter_options(parser):
    parser.add_argument(
        "--or",
        "-o",
        type=str,
        help="Search for any of these strings",
        action="append",
        dest="additional_terms",
    )
    parser.add_argument(
        "--exact",
        "-x",
        action="store_true",
        default=[],
        help="search for exact string",
    )


def csv(s: str) -> List[str]:
    return s.split(",")


PARSER = argparse.ArgumentParser(description="")

parsers = PARSER.add_subparsers(dest="command")

PARSER.add_argument(
    "--debug", action="store_true", help="Include debug output (to stderr)"
)


drop_parser = parsers.add_parser("drop", help="Delete the database.")

drop_parser = parsers.add_parser("info", help="Display info about the database.")

syn_parser = parsers.add_parser(
    "synonyms", help="Try to work out mappings between words"
)
syn_parser.add_argument(
    "target_csv", type=csv, help="Find sources that contain one of these words"
)
syn_parser.add_argument(
    "source_csv",
    type=csv,
    nargs="?",
    help="Find targets that contain one of these words.",
    default=[],
)


search_parser = parsers.add_parser("search", help="Search the database")
search_parser.add_argument(
    "term", type=str, nargs="*", help="Search strings (SQLITE full text search)"
)
display_limit = search_parser.add_mutually_exclusive_group()
display_limit.add_argument(
    "-S", "--only-source", action="store_true", help="Only show the source results"
)
display_limit.add_argument(
    "-T", "--only-target", action="store_true", help="Only show the target results"
)

search_parser.add_argument(
    "--skip", type=int, metavar="SKIP", help="Output one out of SKIP results"
)
search_parser.add_argument("--words", "-w", action="store_true")
filter_options(search_parser)


search_parser.add_argument(
    "--count",
    "-c",
    action="store_true",
    default=False,
    help="Output the number of results",
)
search_parser.add_argument(
    "--group",
    "-g",
    type=str,
    action="append",
    help="Count the number of results that contain this.",
)
search_parser.add_argument(
    "--max", "-m", type=int, help="Return searches with this many words"
)


language = search_parser.add_mutually_exclusive_group()

language.add_argument(
    "--source", action="store_true", default=False, help="Only search source language"
)
language.add_argument(
    "--target", action="store_true", default=False, help="Only search target"
)


load_parser = parsers.add_parser("load", help="Create database")
load_parser.add_argument("en", type=str)
load_parser.add_argument("de", type=str)
load_parser.add_argument("--limit", "-n", type=int, help="Only insert this many values")

tmx_parser = parsers.add_parser("loadtmx", help="Create database from tmx file")
tmx_parser.add_argument("file", type=str)
tmx_parser.add_argument("--limit", "-n", type=int, help="Only insert this many values")


data_dir = os.path.join(os.environ["HOME"], ".parcorp")
filename = os.path.join(data_dir, "data.sql")


def load(args):
    with open(args.en) as source_stream:
        with open(args.de) as target_stream:
            os.unlink(filename)
            connection = sqlite3.connect(filename)
            create_table(connection)

            for index, (source, target) in enumerate(
                zip(source_stream, target_stream)
            ):
                if args.limit is not None and index > args.limit:
                    break

                if index % 1000 == 0:
                    print(index)

                sql_insert_pair(connection, source, target)

            connection.commit()


def load_tmx(args):
    # pylint: disable=too-many-branches

    TU, VALUE1, VALUE2 = "tu", "tu1", "tu2"

    LOGGER.debug("Opening %r", filename)
    connection = sqlite3.connect(filename)
    create_table(connection)

    with open(args.file, "br") as stream:
        state = None

        string1 = string2 = ""
        index = 0
        start = time.time()
        for event, element in lxml.etree.iterparse(
            stream, events=("start", "end")
        ):  # pylint: disable=c-extension-no-member

            if index % 10000 == 0:
                connection.commit()
            if event == "start":
                if element.tag == "tu":
                    string1 = string2 = ""
                    state = TU
                elif element.tag == "tuv":
                    if state == TU:
                        state = VALUE1
                    elif state == VALUE1:
                        state = VALUE2
                    else:
                        raise ValueError(state)
            else:
                if element.tag == "seg":
                    if state == VALUE1:
                        string1 += element.text
                    elif state == VALUE2:
                        string2 += element.text
                    else:
                        raise ValueError(state)
                elif element.tag == "tu":
                    sql_insert_pair(connection, string2, string1)
                    index += 1
                    if args.limit and index > args.limit:
                        break
                    if index % 1000 == 0:
                        taken = time.time() - start
                        print(
                            "\r{} items inserted in {:.1f} seconds. {:.1f} item/s".format(
                                index, taken, index * 1.0 / taken
                            )
                        )
                elif element.tag in ("header", "tuv"):
                    continue
                else:
                    raise ValueError(element.tag)

            if event == "end":
                element.clear()

    connection.commit()


def main():
    args = PARSER.parse_args()
    if args.debug:
        logging.basicConfig(level=logging.DEBUG)

    if not os.path.isdir(data_dir):
        os.mkdir(data_dir)
    elif args.command == "load":
        load(args)
    elif args.command == "loadtmx":
        load_tmx(args)
    elif args.command == "drop":
        os.unlink(filename)
    elif args.command == "info":
        connection = sqlite3.connect(filename)
        cursor = connection.cursor()
        cursor.execute("select count(*) from translation")
        print(cursor.fetchall())
    elif args.command == "search":
        search(args)
    elif args.command == "synonyms":
        synonyms(args)
    else:
        raise ValueError(args.command)


def synonyms(args):
    "Try to find the synonyms fora word"
    connection = sqlite3.connect(filename)
    sql, sql_terms = build_search_sql([], args.target_csv)
    cursor = connection.cursor()
    LOGGER.debug("Running sql %r %r", sql, sql_terms)
    cursor.execute(sql, sql_terms)

    counts = collections.Counter()
    for target, source in cursor.fetchall():
        target = strip_punct(target)
        source = strip_punct(source)
        target_words = get_words(target)
        source_words = get_words(source)

        counts.update(
            [
                (g, e)
                for g in target_words
                for e in source_words
                if e in args.target_csv
                and (not args.source_csv or g in args.source_csv)
            ]
        )

    for pair in sorted(counts, key=counts.get, reverse=True):
        print(pair, counts[pair])


def strip_punct(s: str) -> str:
    for c in ".,!":
        s = s.replace(c, "")
    return s


def get_words(s: str) -> List[str]:
    return [w.lower() for w in s.split()]


def build_search_sql(target_terms, source_terms):
    def build_condition(field, terms):
        condition_template = " or ".join(["{} MATCH ?".format(field)] * len(terms))
        wrapped_condition = "({})".format(condition_template)

        if terms:
            return [wrapped_condition]
        else:
            return []

    target_query = build_condition("target", target_terms)
    source_query = build_condition("source", source_terms)

    sql = "select target, source from translation where {} order by max(length(target), length(source))".format(
        " or ".join(target_query + source_query)
    )

    return sql, target_terms + source_terms


def search(args):
    args.additional_terms = args.additional_terms or []
    connection = sqlite3.connect(filename)
    cursor = connection.cursor()
    terms = [" ".join(args.term)] + (args.additional_terms or [])

    if args.exact:
        terms = ['"{}"'.format(t) for f in terms]

    if args.target:
        target_terms = terms[:]
        source_terms = []
    elif args.source:
        target_terms = []
        source_terms = terms[:]
    else:
        target_terms = terms[:]
        source_terms = terms[:]

    sql, sql_terms = build_search_sql(target_terms, source_terms)

    LOGGER.debug("Running sql {!r}".format(sql))
    cursor.execute(sql, sql_terms)

    if args.count:
        print(len(cursor.fetchall()))
    else:
        words = collections.Counter()
        groups = collections.defaultdict(int)
        for index, (target, source) in enumerate(cursor.fetchall()):
            if args.skip is not None and index % args.skip != 0:
                continue

            if args.max is not None:
                if min(len(target.split(" ")), len(source.split(" "))) < args.max:
                    continue

            if args.group:
                containing_word, *_ = itertools.chain(
                    [w for w in args.group if w in target or w in source], [None]
                )
                if containing_word:
                    groups[containing_word] += 1
                    continue
                else:
                    groups["unknown"] += 1

            if args.words:
                if args.only_source:
                    words.update(source.split())
                elif args.only_target:
                    words.update(target.split())
                else:
                    words.update(source.split())
                    words.update(target.split())
            else:
                if args.only_source:
                    print(f"{source}")
                elif args.only_target:
                    print(f"{target}")
                else:
                    print(f"{target} -> {source}")

        if args.words:
            for word in sorted(words, key=words.get, reverse=True):
                print(word, words[word])
        else:
            for word, count in groups.items():
                print(f"{word}: {count}")


def create_table(connection):
    connection.execute(
        "create virtual table translation using fts3(source text, target text)"
    )


def sql_insert_pair(connection, source, target):
    LOGGER.debug("Inserting %r, %r", source, target)
    connection.execute(
        "insert into translation(source, target) values (?, ?)", (source, target)
    )


if __name__ == '__main__':
    main()
