# Semantic search

Full-text search needs the words in the document. Semantic search also finds documents
that mean the same thing in different words, so "bounce the vcenter daemon" reaches a
script that says `systemctl restart vpxd`.

It is optional and off until built. Everything runs on this machine: a small static
embedding model on the CPU, and vectors stored in the same SQLite file through the
`sqlite-vec` extension. There is no service, no GPU and no network call at search time.

## Build

```bash
cd ~/xtoo
source .venv/bin/activate
python -m pip install -e '.[vectors]'
xtoo embed
```

The first run downloads the embedding model (about 30 MB) from Hugging Face; after
that it is cached under `~/.cache/huggingface` and no network is needed again. Nothing
else in Xtoo makes a network call, and a blocked download leaves the rest unaffected.

### When the download is intercepted

A managed network that inspects TLS presents its own certificate, which Python does not
trust by default, so the download fails with `CERTIFICATE_VERIFY_FAILED` even though
the site is reachable. Check before running a long job:

```bash
python -c "import huggingface_hub as h; print(h.hf_hub_download('minishlab/potion-base-8M', 'config.json'))"
```

A path means you are fine. A certificate error means Python needs your organisation's
root certificate, which your IT department can supply as a `.crt` or `.pem` file:

```bash
export SSL_CERT_FILE=/path/to/corporate-root.pem
export REQUESTS_CA_BUNDLE=/path/to/corporate-root.pem
xtoo embed
```

Both variables are set because different libraries read different ones. Add them to
`~/.bashrc` to keep them. Do not disable certificate verification instead; that hides
real failures and is usually against policy.

### Fully offline

If the download cannot be made to work, fetch the model elsewhere and copy the folder
in, then name the directory instead of the model:

```bash
xtoo embed --model /home/YOUR_LINUX_USER/models/potion-base-8M
```

The model is recorded in the index, so searches use the same one automatically and
`--model` is not needed again. Naming a different model later rebuilds every vector,
because vectors from two models cannot be compared.

`xtoo embed` reads documents from the index rather than from disk, embeds the first
6,000 characters of each as up to four overlapping windows, and reports progress. It is
safe to interrupt: rerunning continues where it stopped. It also re-embeds documents
whose text changed and drops vectors for documents that were removed, so running it
after a scan keeps it current.

Measured on 20,000 mail-sized documents on a laptop CPU:

| Measure | Value |
| --- | --- |
| Model | `minishlab/potion-base-8M`, 256 dimensions |
| Build speed | about 490 documents per second, so roughly 15 minutes for 400,000 |
| Index growth | about 1.3 KB per document, so roughly 0.5 GB for 400,000 |
| Query time | about 100 ms at 40,000 vectors, rising to about 1.5 seconds at 850,000 |

Nearest-neighbour search reads every stored vector, so query time grows with the size
of the library rather than staying flat. That is the cost of having no index server;
full-text search is unaffected and stays in the low hundreds of milliseconds. Each
document is embedded as at most two windows to keep that scan half the size it would
otherwise be.

## Use

In the browser, tick **Meaning** in the search bar. The toggle appears only once
vectors exist. From the terminal or an assistant:

```bash
xtoo search --meaning bounce the vcenter daemon
```

Results combine the full-text and semantic rankings by reciprocal rank fusion, rather
than replacing one with the other: an exact keyword match still wins, while a
paraphrase that full-text search would miss is now reachable. The MCP tools use the
combined ranking automatically when vectors are built.

## Limitations

| Limitation | Detail |
| --- | --- |
| Only the start of a document | Two windows of 2,000 characters. A long report's later sections are found by full-text search but not by meaning. |
| Static embeddings | Faster than a transformer by orders of magnitude, and correspondingly less precise. Good for recall, not for ranking subtleties. |
| No entity filter in the semantic arm | Linking by identifier applies to full-text results; a semantic query narrows by file type, and conversations are grouped as usual. |
| Rebuild after bulk changes | Vectors follow the index, so run `xtoo embed` again after a large scan. `xtoo embed --rebuild` starts from nothing. |
