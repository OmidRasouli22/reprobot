# ReproBot

Turns GitHub bug reports into failing tests that prove the bug.

ReproBot reads an issue, sets up the project in an isolated Docker container,
explores the code, and writes a test that fails today because of the bug and
will pass once the bug is fixed.

**Status:** early development.

## License

[MIT](LICENSE)
