import logging
from logging import getLogger

import click
from tabulate import tabulate

from lifeweeker import Visitor

logger = getLogger(__name__)


class Context:
    def __init__(self):
        self.ticket: str = None
        self.visitor: Visitor = None


@click.group()
@click.option("-t", "--ticket", help="API ticket")
@click.option("-v", "--verbosity", default="INFO", help="Logging level")
@click.pass_context
def main(ctx, **argv):
    verbosity = argv.pop("verbosity").upper()
    logging.basicConfig(format='%(asctime)s %(message)s', level=verbosity)

    ticket = argv.pop("ticket", None)

    ctx.obj = Context()
    ctx.obj.visitor = Visitor(ticket=ticket)


@main.command("search")
@click.option("--keyword", "-k", type=click.STRING, required=True)
@click.pass_context
def search(ctx, **argv):
    keyword = argv.pop("keyword")
    logger.info(f"keyword:{type(keyword)}")

    data = ctx.obj.visitor.search_content(keyword)

    table = []
    for item in data:
        category = item["category"]
        name = item["contentName"]
        title = item["contentTitle"]
        content_id = item["contentId"]
        table.append((category, name, title, content_id))

    click.echo(tabulate(table))


@main.command("save-column-audio")
@click.option("--id", type=click.INT, required=True)
@click.pass_context
def save_show(ctx, **argv):
    column_id = argv.pop("id")
    ctx.obj.visitor.save_column_audio(column_id)


@main.command("save-column-article")
@click.option("--id", type=click.INT, required=True)
@click.pass_context
def save_show(ctx, **argv):
    column_id = argv.pop("id")
    ctx.obj.visitor.save_column_article(column_id)


if __name__ == "__main__":
    main()
