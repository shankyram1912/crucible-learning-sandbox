/**
 * Single-source-of-truth map from repo Markdown files (../specs, ../guides, ../todolist.md)
 * to Starlight URL slugs — zero copied .md files on disk.
 */
export const BASE = '/crucible-learning-sandbox';
export const OWNER_REPO = 'shankyram1912/crucible-learning-sandbox';
export const GH_BLOB = `https://github.com/${OWNER_REPO}/blob/main/`;
export const GH_TREE = `https://github.com/${OWNER_REPO}/tree/main/`;

export interface PageEntry {
  /** Path relative to repo root */
  source: string;
  /** Starlight URL slug (empty string = landing page) */
  slug: string;
  /** Sidebar / page title override (falls back to first # H1 in source) */
  title?: string;
  description?: string;
}

export const PAGES: PageEntry[] = [
  // Guides & Roadmap
  {
    source: 'guides/lsb-cli-user-guide.md',
    slug: 'guides/cli',
    title: 'lsb CLI User Guide',
    description: 'Install, sign in, and run the lsb command-line interface.',
  },
  {
    source: 'todolist.md',
    slug: 'roadmap/todolist',
    title: 'Build Sequence & To-Do',
    description: 'Day-0 bootstrap steps, Self Service API build order, and verification status.',
  },

  // 01 — Business Requirements (BRS)
  {
    source: 'specs/01-brs/brs-master.md',
    slug: 'brs/master',
    title: 'BRS Master & Conceptual Framework',
    description: 'Business problem, layered conceptual framework, personas, and core rules.',
  },
  {
    source: 'specs/01-brs/brs-it-admin-cuj.md',
    slug: 'brs/it-admin-cuj',
    title: 'IT Admin Journeys (CUJ)',
    description: 'Catalogs, templates, cost tags, and Playground Folder governance.',
  },
  {
    source: 'specs/01-brs/brs-bu-admin-cuj.md',
    slug: 'brs/bu-admin-cuj',
    title: 'BU Admin Journeys (CUJ)',
    description: 'Playground creation, group mapping, service evolution, capacity, and decommissioning.',
  },

  // 02 — Technical Design (TDD)
  {
    source: 'specs/02-tdd/tdd-master.md',
    slug: 'tdd/master',
    title: 'TDD Master (Terraform & IAM)',
    description: 'Guiding principles for Terraform, billing labels, dynamic tags, Firestore split, and IAM.',
  },
  {
    source: 'specs/02-tdd/tdd-control-tower/tdd-control-tower-master.md',
    slug: 'tdd/control-tower',
    title: 'Control Tower Day-0 Bootstrap',
    description: 'Step-by-step Day-0 bootstrap architecture and Terraform operations.',
  },
  {
    source: 'specs/02-tdd/tdd-tags-labels/tdd-tags-labels-master.md',
    slug: 'tdd/tags-labels',
    title: 'Tag & Label Binding Deep Dive',
    description: 'Two-sided Tag User checks, dynamic regex validation, label sync, and live GCP behavior.',
  },
  {
    source: 'specs/02-tdd/tdd-playground/tdd-playground-master.md',
    slug: 'tdd/playground-pipeline',
    title: 'Playground Terraform Pipeline',
    description: 'Cloud Build execution identities, secured source, state isolation, and reliability.',
  },
  {
    source: 'specs/02-tdd/tdd-playground/tdd-playground-services.md',
    slug: 'tdd/playground-services',
    title: 'Playground GCP Services',
    description: 'Per-service Terraform modules, prerequisites, singletons, and app resources.',
  },
  {
    source: 'specs/02-tdd/tdd-data/tdd-data-master.md',
    slug: 'tdd/data',
    title: 'Firestore Data Design',
    description: 'Config database vs. runtime-and-jobs database schema and invariants.',
  },

  // 02 — TDD: Self Service APIs
  {
    source: 'specs/02-tdd/tdd-apis/tdd-apis-master.md',
    slug: 'tdd/apis/master',
    title: 'APIs Master',
    description: 'REST interface principles, domain map, and lsb CLI mapping.',
  },
  {
    source: 'specs/02-tdd/tdd-apis/tdd-apis-common-stack.md',
    slug: 'tdd/apis/common-stack',
    title: 'Common: Runtime Stack',
    description: 'FastAPI, Pydantic, Typer, and deployment conventions.',
  },
  {
    source: 'specs/02-tdd/tdd-apis/tdd-apis-common-auth.md',
    slug: 'tdd/apis/common-auth',
    title: 'Common: Authentication',
    description: 'Google ID token verification, allowed audiences, and caller context.',
  },
  {
    source: 'specs/02-tdd/tdd-apis/tdd-apis-common-acl.md',
    slug: 'tdd/apis/common-acl',
    title: 'Common: Access Control (ACL)',
    description: 'Settings-driven role ACL, one-route-one-operation rule, and default matrix.',
  },
  {
    source: 'specs/02-tdd/tdd-apis/tdd-apis-common-models.md',
    slug: 'tdd/apis/common-models',
    title: 'Common: Models & Errors',
    description: 'RequestContext, personas, standard error envelope, and correlation headers.',
  },
  {
    source: 'specs/02-tdd/tdd-apis/tdd-apis-common-config.md',
    slug: 'tdd/apis/common-config',
    title: 'Common: Configuration Settings',
    description: 'Environment settings from initialize.env and LSB_* overrides.',
  },
  {
    source: 'specs/02-tdd/tdd-apis/tdd-apis-common-cli.md',
    slug: 'tdd/apis/common-cli',
    title: 'Common: lsb CLI Conventions',
    description: 'Command layout, exit codes, ADC sign-in, and JSON output.',
  },
  {
    source: 'specs/02-tdd/tdd-apis/tdd-apis-common-jobs.md',
    slug: 'tdd/apis/common-jobs',
    title: 'Common: Jobs (Sync, Async, Terraform)',
    description: 'Interim job kinds, lifecycle, leases, locks, and handler contract.',
  },
  {
    source: 'specs/02-tdd/tdd-apis/tdd-apis-health.md',
    slug: 'tdd/apis/health',
    title: 'Domain: Health (01–03)',
    description: 'Liveness, Firestore database readiness, and cached service status.',
  },
  {
    source: 'specs/02-tdd/tdd-apis/tdd-apis-platform-users.md',
    slug: 'tdd/apis/platform-users',
    title: 'Domain: Platform Users (04)',
    description: 'In-memory admin roster, optional live directory role checks, and platform roles routes.',
  },
];
