# parcorp

A tool to explore parralel corpuses.

# Motivation

A lot can be learned by looking at the same text translated into different languages. Such "rosetta stones" have when collated have a name: parallel corpuses.

# Data sources

The main data sources that the author has used with this program are subtitle data collated by someone else, and the transcripts of the EU parliament - which is helpfully translated into thirteen languages.

For aligned subtitles: http://opus.nlpl.eu/ is a good source. Use the `loadtmx` command and tmx format.

Data must be loaded once and only once. Use the `load` or `loadtmx` commands. To reload data, delete `$HOME/.parcorp/data.sql`.
