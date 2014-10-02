import ConfigParser
import StringIO


def make_configparser(config):
    parser = ConfigParser.ConfigParser()
    unindented = "\n".join(line.strip() for line in config.splitlines())
    text = StringIO.StringIO(unindented)
    parser.readfp(text)
    return parser
