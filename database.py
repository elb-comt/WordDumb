import sqlite3
from pathlib import Path
from typing import Iterator

try:
    from .utils import load_plugin_json
except ImportError:
    from utils import load_plugin_json


def get_ll_path(asin: str, book_path: str) -> Path:
    return Path(book_path).parent.joinpath(f"LanguageLayer.en.{asin}.kll")


def create_lang_layer(
    asin: str, book_path: str, acr: str, revision: str
) -> tuple[sqlite3.Connection, Path]:
    db_path = get_ll_path(asin, book_path)
    ll_conn = sqlite3.connect(":memory:")
    ll_conn.executescript(
        """
        CREATE TABLE metadata (
            key TEXT,
            value TEXT
        );

        CREATE TABLE glosses (
            start INTEGER PRIMARY KEY,
            end INTEGER,
            difficulty INTEGER,
            sense_id INTEGER,
            low_confidence BOOLEAN
        );
        """
    )

    metadata = [
        ("acr", acr),
        ("targetLanguages", "en"),
        ("sidecarRevision", "9"),
        ("bookRevision", revision),
        ("sourceLanguage", "en"),
        ("enDictionaryVersion", "2016-09-14"),
        ("enDictionaryRevision", "57"),
        ("enDictionaryId", "kll.en.en"),
        ("sidecarFormat", "1.0"),
    ]
    ll_conn.executemany("INSERT INTO metadata VALUES (?, ?)", metadata)
    return ll_conn, db_path


def insert_lemma(ll_conn: sqlite3.Connection, data: tuple[int, int, int, int]) -> None:
    ll_conn.execute(
        """
        INSERT INTO glosses (start, end, difficulty, sense_id, low_confidence)
        VALUES (?, ?, ?, ?, 0)
        """,
        data,
    )


def get_x_ray_path(asin: str, book_path: str) -> Path:
    return Path(book_path).parent.joinpath(f"XRAY.entities.{asin}.asc")


def create_x_ray_db(
    asin: str,
    book_path: str,
    lang: str,
    plugin_path: Path,
    prefs: dict[str, str],
    wiki_name: str,
    mediawiki_api: str,
) -> tuple[sqlite3.Connection, Path]:
    db_path = get_x_ray_path(asin, book_path)
    x_ray_conn = sqlite3.connect(":memory:")
    x_ray_conn.executescript(
        """
    PRAGMA user_version = 1;

    CREATE TABLE book_metadata (
    srl INTEGER,
    erl INTEGER,
    has_images TINYINT,
    has_excerpts TINYINT,
    show_spoilers_default TINYINT,
    num_people INTEGER,
    num_terms INTEGER,
    num_images INTEGER,
    preview_images TEXT);

    CREATE TABLE entity (
    id INTEGER PRIMARY KEY,
    label TEXT,
    loc_label INTEGER,
    type INTEGER,
    count INTEGER,
    has_info_card TINYINT);

    CREATE TABLE entity_description (
    text TEXT,
    source_wildcard TEXT,
    source INTEGER,
    entity INTEGER PRIMARY KEY);

    CREATE TABLE entity_excerpt (
    entity INTEGER,
    excerpt INTEGER);

    CREATE TABLE excerpt (
    id INTEGER PRIMARY KEY,
    start INTEGER,
    length INTEGER,
    image TEXT,
    related_entities TEXT,
    goto INTEGER);

    CREATE TABLE occurrence (
    entity INTEGER,
    start INTEGER,
    length INTEGER);

    CREATE TABLE source (
    id INTEGER PRIMARY KEY,
    label INTEGER,
    url INTEGER,
    license_label INTEGER,
    license_url INTEGER);

    CREATE TABLE string (
    id INTEGER,
    language TEXT,
    text TEXT);

    CREATE TABLE type (
    id INTEGER PRIMARY KEY,
    label INTEGER,
    singular_label INTEGER,
    icon INTEGER,
    top_mentioned_entities TEXT);

    INSERT INTO entity (id, loc_label, has_info_card) VALUES(0, 1, 0);
    INSERT INTO source (id, label, url) VALUES(0, 5, 20);
    INSERT INTO source VALUES(1, 6, 21, 7, 8);
    """
    )

    str_list = load_plugin_json(plugin_path, "data/x_ray_strings.json")
    str_list.append(
        [
            21,
            "en",
            f"https://zh.wikipedia.org/zh-{prefs['zh_wiki_variant']}/%s"
            if lang == "zh"
            else f"https://{lang}.wikipedia.org/wiki/%s",
        ]
    )
    str_list.append([22, "en", f"{mediawiki_api.split('/', 1)[0]}/wiki/%s"])
    x_ray_conn.execute(
        """
        INSERT INTO source (id, label, url, license_label, license_url)
        VALUES(2, 4, 22, 7, 8)
        """
    )
    x_ray_conn.executemany("INSERT INTO string VALUES(?, ?, ?)", str_list)
    if wiki_name != "Wikipedia":
        x_ray_conn.execute("UPDATE string SET text = ? WHERE id = 4", (wiki_name,))
    return x_ray_conn, db_path


def create_x_indices(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE INDEX idx_entity_type ON entity(type ASC);
        CREATE INDEX idx_entity_excerpt ON entity_excerpt(entity ASC);
        CREATE INDEX idx_occurrence_start ON occurrence(start ASC);
        PRAGMA optimize;
        """
    )


def insert_x_book_metadata(
    conn: sqlite3.Connection, erl: int, num_images: int, preview_images: str | None
) -> None:
    num_people = 0
    num_terms = 0
    for (num,) in conn.execute("SELECT count(*) FROM entity WHERE type = 1"):
        num_people = num
    for (num,) in conn.execute("SELECT count(*) FROM entity WHERE type = 2"):
        num_terms = num
    conn.execute(
        "INSERT INTO book_metadata VALUES(0, ?, ?, 0, 0, ?, ?, ?, ?)",
        (erl, num_images > 0, num_people, num_terms, num_images, preview_images),
    )


def insert_x_entities(
    conn: sqlite3.Connection, data: Iterator[tuple[int, str, int, int]]
) -> None:
    conn.executemany(
        """
        INSERT INTO entity (id, label, type, count, has_info_card)
        VALUES(?, ?, ?, ?, 1)
        """,
        data,
    )


def insert_x_entity_description(
    conn: sqlite3.Connection, data: tuple[str, str, int | None, int]
) -> None:
    conn.execute("INSERT INTO entity_description VALUES(?, ?, ?, ?)", data)


def insert_x_occurrences(
    conn: sqlite3.Connection, data: Iterator[tuple[int, int, int]]
) -> None:
    conn.executemany("INSERT INTO occurrence VALUES(?, ?, ?)", data)


def get_top_ten_entities(conn: sqlite3.Connection, entity_type: int) -> str:
    entity_ids = []
    for (entity_id,) in conn.execute(
        "SELECT id FROM entity WHERE type = ? ORDER BY count DESC LIMIT 10",
        (entity_type,),
    ):
        entity_ids.append(entity_id)
    return ",".join(map(str, entity_ids))


def insert_x_types(conn: sqlite3.Connection) -> None:
    insert_x_type(conn, (1, 14, 15, 1, get_top_ten_entities(conn, 1)))
    insert_x_type(conn, (2, 16, 17, 2, get_top_ten_entities(conn, 2)))


def insert_x_type(
    conn: sqlite3.Connection, data: tuple[int, int, int, int, str]
) -> None:
    conn.execute("INSERT INTO type VALUES(?, ?, ?, ?, ?)", data)


def insert_x_excerpt_image(
    conn: sqlite3.Connection, data: tuple[int, int, int, str, int]
) -> None:
    conn.execute(
        "INSERT INTO excerpt (id, start, length, image, goto) VALUES(?, ?, ?, ?, ?)",
        data,
    )


def save_db(source: sqlite3.Connection, dest_path: Path) -> None:
    source.commit()
    dest = sqlite3.connect(dest_path)
    with dest:
        source.backup(dest)
        dest.execute("PRAGMA optimize")
    source.close()
    dest.close()


def compare_klld_metadata(
    conn_a: sqlite3.Connection, conn_b: sqlite3.Connection, key: str
) -> bool:
    sql = "SELECT value FROM metadata WHERE key = ?"
    for value_a in conn_a.execute(sql, (key,)):
        for value_b in conn_b.execute(sql, (key,)):
            return value_a == value_b
    return False


def is_same_klld(path_a: Path, path_b: Path) -> bool:
    conn_a = sqlite3.connect(path_a)
    conn_b = sqlite3.connect(path_b)
    for key in ["lemmaLanguage", "definitionLanguage", "version"]:
        if not compare_klld_metadata(conn_a, conn_b, key):
            conn_a.close()
            conn_b.close()
            return False
    conn_a.close()
    conn_b.close()
    return True
