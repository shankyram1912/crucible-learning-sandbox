/**
 * Single-source-of-truth map from repo Markdown files (../specs, ../src, ../guides, ../todolist.md)
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
  // 01 — Conceptual Architecture (specs/01-brs/)
  {
    source: 'specs/01-brs/brs-master.md',
    slug: 'brs/master',
    title: 'Business Requirements & Conceptual Framework',
    description: 'The business problem, layered conceptual framework, personas, playground organization, and core rules.',
  },
  {
    source: 'specs/01-brs/brs-it-admin-cuj.md',
    slug: 'brs/it-admin-cuj',
    title: 'IT Admin Journeys',
    description: 'Service catalog, playground templates, cost centers and categories, Playground Folders, and tracked jobs.',
  },
  {
    source: 'specs/01-brs/brs-bu-admin-cuj.md',
    slug: 'brs/bu-admin-cuj',
    title: 'BU Admin & Playground Admin Journeys',
    description: 'Playground creation, budgets, service configuration, capacity expansion, portal access suspension, and decommissioning.',
  },
  {
    source: 'specs/01-brs/brs-student-cuj.md',
    slug: 'brs/student-cuj',
    title: 'Student & Designated User Journeys',
    description: 'Workspace initialization on first entry, singleton resources, app containers, per-user allowances, and tracked jobs.',
  },

  // 02 — Specifications (specs/02-tdd/)
  {
    source: 'specs/02-tdd/tdd-master.md',
    slug: 'tdd/master',
    title: 'Control Tower TDD: Terraform and IAM Principles',
    description: 'Guiding principles for Terraform, billing labels, dynamic tags, Firestore databases, and IAM.',
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
    title: 'Tag and Label Binding',
    description: 'Two-sided Tag User checks, dynamic regex validation, label copy at project creation, and GCP behavior.',
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
    description: 'Per-service Terraform modules, prerequisites, singleton resources, and app resources.',
  },

  // 02 — Specifications: Firestore Data
  {
    source: 'specs/02-tdd/tdd-data/tdd-data-master.md',
    slug: 'tdd/data',
    title: 'Firestore Data Design (Master)',
    description: 'Two-database trust boundary, conceptual configuration domains, ER model, and lifecycle invariants.',
  },
  {
    source: 'specs/02-tdd/tdd-data/tdd-data-config.md',
    slug: 'tdd/data/config',
    title: 'Configuration Entities (Config DB)',
    description: 'Physical Firestore collections, document JSON schemas, retrieval patterns, and composite indexes for lsb-control-tower-config-db.',
  },

  // 02 — Specifications: Self Service APIs
  {
    source: 'specs/02-tdd/tdd-apis/tdd-apis-master.md',
    slug: 'tdd/apis/master',
    title: 'Self Service APIs (Master)',
    description: 'REST interface principles, domain map, and lsb CLI mapping.',
  },
  {
    source: 'specs/02-tdd/tdd-apis/tdd-apis-cuj-map.md',
    slug: 'tdd/apis/cuj-map',
    title: 'CUJ to Operation Map',
    description: 'Reusable API operation catalog mapped to IT Admin, BU Admin, Playground Admin, and Student journeys.',
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

  // 03 — Deployment & User Guides (src/.../README.md, guides/, todolist.md)
  {
    source: 'src/terraform/control-tower/README.md',
    slug: 'deploy/control-tower',
    title: 'Control Tower Day-0 Bootstrap Runbook',
    description: 'Run Day-0 Terraform bootstrap operations in Google Cloud Shell.',
  },
  {
    source: 'src/api/README.md',
    slug: 'deploy/api',
    title: 'lsb-api Developer & Local Server Guide',
    description: 'Install, test, and run the FastAPI Self Service APIs server locally.',
  },
  {
    source: 'src/cli/README.md',
    slug: 'deploy/cli',
    title: 'lsb-cli Developer Guide',
    description: 'Work on and install the lsb command-line client from source.',
  },
  {
    source: 'guides/lsb-cli-user-guide.md',
    slug: 'guides/cli',
    title: 'lsb CLI User Guide',
    description: 'Install lsb, sign in with Application Default Credentials, and run commands.',
  },
  {
    source: 'todolist.md',
    slug: 'roadmap/todolist',
    title: 'Build Sequence & Status',
    description: 'Day-0 bootstrap steps, Self Service API build order, and verification status.',
  },
  {
    source: 'specs/roadmap/dedicated-playground-sandboxes.md',
    slug: 'roadmap/dedicated-playground-sandboxes',
    title: 'Dedicated Playground Sandboxes',
    description: 'First principles, tag-based progressive Org Policy relaxation, and two-layer bulk provisioning for 25,000+ personal GCP projects.',
  },
];
