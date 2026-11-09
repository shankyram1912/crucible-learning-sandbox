# LSB Control Tower TDD: APIs, Common CLI

> Parent: [tdd-apis-master.md](tdd-apis-master.md)

Conventions every `lsb` command follows: terminal output, global options and exit codes. Domain specs define their own commands and output examples; exceptions (for example `lsb health db` exit code `1`) are stated there.

---

## 1. Terminal output

### 1.1 Color scheme
| Meaning | Color | Symbol |
|---|---|---|
| Done / succeeded | Green | `✔` |
| Running / applying | Blue (spinner) | `⠋` |
| Created, waiting for ready | Cyan | `◐` |
| Getting ready | Yellow | `…` |
| Pending | Gray | `○` |
| Skipped | Dim | `–` |
| Failed / error | Red | `✖` |
| Identifiers (cohort, project, group) | Bold magenta | |

### 1.2 Example: define cohort (live, updating in place)
```
$ lsb cohort define cs100 --playground learning-sandbox --projects 1 \
      --billing XXXXXX-XXXXXX-XXXXXX \
      --members admins=seed/cs100-admins.csv --members students=seed/cs100-students.csv

 Define cohort cs100 (CS 100) in playground learning-sandbox    job-20261108-0001

  ✔ Pre-check                         template standard, 2 groups, 3 members        0.8s
  ◐ Create project cs100-p01          created, linking billing                      22s
  ○ Create preset groups              grp-ls-cs-cs100-admins, grp-ls-cs-cs100-students
  ○ Load members                      3 members

  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 1/4
```

### 1.3 Example: pre-check failure
```
$ lsb service enable cs100 vertex-search

  ✖ Pre-check failed (2 problems)
    • vertex-search requires gcs, which is not enabled on cs100
    • group student-admins has no members

  Nothing was changed.
```

---

## 2. Global options
| Option | Effect |
|---|---|
| `--json` | Print the raw API response, no colors |
| `--no-wait` | For mutating commands, return the `job_id` without watching |
| `--api <url>` | Override `LSB_API_URL` |
| `NO_COLOR=1` | Disable colors (standard convention) |

---

## 3. Exit codes
| Code | Meaning |
|---|---|
| `0` | Success (job `SUCCEEDED`, or read command OK) |
| `1` | Job `FAILED` |
| `2` | Request rejected (`400`, `401`, `403`, `404`, `409`, `422`) |
| `3` | API unreachable or `500` |
