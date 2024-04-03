from slugify import slugify
from flask import Flask, render_template, redirect, request, url_for, abort
from pathlib import Path
import os

import duckdb

app = Flask(__name__)

con = duckdb.connect("demo.db")
con.sql("CREATE TABLE IF NOT EXISTS databases (label VARCHAR(50), name VARCHAR(50), owner VARCHAR(50))")


@app.route("/")
def home():
    con.execute("SELECT * FROM databases")
    databases = con.fetchall()
    return render_template("index.html", databases=databases)


@app.route("/databases/<owner>/<db_slug>")
def read_database(owner, db_slug):
    match = con.execute("SELECT label FROM databases WHERE name = ?", [db_slug]).fetchone()

    if match is None:
        abort(404)

    c = get_motherduck_con(owner)
    
    schema_tables = c.execute('SELECT table_name FROM information_schema.tables WHERE table_catalog=? AND table_schema=?', [owner, db_slug]).fetchall()
    schema_tables = [item[0] for item in schema_tables]
    
    table = request.args.get("tbl")
    
    if table is None:
        table = schema_tables[0]

    try:
        df = c.sql("FROM {}.{}".format(db_slug, table)).df()
        nrow, ncol = df.shape
        return render_template(
            "database.html",
            db=db_slug,
            label=match[0],
            table=table,
            ncol=ncol,
            nrow=nrow,
            cols=df.columns,
            records=df.to_records(index=False),
            tables=schema_tables,
            owner=owner
        )
    except duckdb.duckdb.CatalogException:
        abort(404)
    finally:
        c.close()




@app.route("/upload/database", methods=["POST"])
def upload_database():
    name = request.form.get("name")
    username = request.form.get("username")
    file = request.files["file"]

    table = slugify(Path(file.filename).stem, separator="_")
    db_name = slugify(name, separator="_")

    with get_motherduck_con(username) as c:
        r = c.read_csv(file.stream)
        c.sql("CREATE SCHEMA {}".format(db_name))
        c.sql("CREATE TABLE {}.{} AS SELECT * FROM r".format(db_name, table))

    con.execute("INSERT INTO databases VALUES ($1, $2, $3)", [name, db_name, username])
    return redirect(url_for("home"))


@app.route("/upload/table", methods=["POST"])
def upload_table():
    db_slug = request.form.get("db")
    owner = request.form.get("owner")
    name = request.form.get("name")
    file = request.files["file"]

    table_slug = slugify(name, separator="_")


    with get_motherduck_con(owner) as c:
        r = c.read_csv(file.stream)
        c.sql("CREATE TABLE {}.{} AS SELECT * FROM r".format(db_slug, table_slug))

    return redirect(url_for("read_database", owner=owner, db_slug=db_slug, tbl=table_slug))

@app.errorhandler(404)
def not_found(e):
    return render_template("404.html")


def get_motherduck_con(username):
    token = os.getenv("MOTHERDUCK_TOKEN")
    return duckdb.connect("md:{}?motherduck_token={}".format(username, token))