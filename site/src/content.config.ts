import { defineCollection } from 'astro:content';
import { docsSchema } from '@astrojs/starlight/schema';
import type { Loader } from 'astro/loaders';
import { readFileSync, existsSync } from 'node:fs';
import { resolve, dirname, posix } from 'node:path';
import { fileURLToPath } from 'node:url';
import { BASE, GH_BLOB, GH_TREE, PAGES } from './pages-map';

const siteSrcDir = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(siteSrcDir, '..', '..');

const sourceToSlug = new Map<string, string>(
  PAGES.map((p) => [p.source.replace(/\\/g, '/'), p.slug]),
);

function rewriteLinks(body: string, sourceRelPath: string): string {
  const fromDir = posix.dirname(sourceRelPath.replace(/\\/g, '/'));
  // Rewrite markdown links `[label](target)` while ignoring regexes like `[a-z](...)`
  return body.replace(/(\[[^\]]+\]\()([^)\s#]+)(#[^)\s]*)?(\))/g, (full, open, target, hash = '', close) => {
    // Skip regex character classes mistaken for links (e.g. `^[a-z]([a-z0-9-]...`)
    if (target.startsWith('[')) return full;
    // Leave external schemes, absolute paths, and pure anchors untouched
    if (/^[a-z][a-z0-9+.-]*:/i.test(target) || target.startsWith('/')) return full;

    const resolved = posix.normalize(posix.join(fromDir === '.' ? '' : fromDir, target));
    const mappedSlug = sourceToSlug.get(resolved);
    if (mappedSlug !== undefined) {
      const url = mappedSlug === '' ? `${BASE}/` : `${BASE}/${mappedSlug}/`;
      return `${open}${url}${hash}${close}`;
    }

    // Any repo file/directory not published as a Starlight page points directly to GitHub
    const absCheck = resolve(repoRoot, resolved);
    if (existsSync(absCheck)) {
      const ghBase = resolved.endsWith('.md') || /\.[a-z0-9]+$/i.test(resolved) ? GH_BLOB : GH_TREE;
      return `${open}${ghBase}${resolved}${hash}${close}`;
    }

    return full;
  });
}

function buildLandingPage() {
  const md = `
Crucible is a self-service Google Cloud learning sandbox platform orchestrated from a central **Control Tower**. Central IT defines governed **Playground Folders**, version-tracked **Service Catalogs**, and **Playground Templates** once — empowering Schools (**BU Admins**), Teaching Assistants (**Playground Admins**), and **Students** to spin up shared-project cloud & AI labs safely inside pooled budgets.

## Read the Specifications

- **[Business Requirements & Conceptual Framework (01-BRS)](${BASE}/brs/master/)** — Layered conceptual model from big-picture governance down to Playground Folders, Playgrounds, project shards, student singleton resources, and app containers.
  - [IT Admin Journeys (CUJ)](${BASE}/brs/it-admin-cuj/) · [BU Admin Journeys (CUJ)](${BASE}/brs/bu-admin-cuj/)
- **[Technical Design Principles (02-TDD)](${BASE}/tdd/master/)** — Terraform execution model, dynamic Resource Manager tags & billing label sync, dual-Firestore split, and least-privilege IAM.
  - [Control Tower Day-0 Bootstrap](${BASE}/tdd/control-tower/) · [Tag & Label Binding Deep Dive](${BASE}/tdd/tags-labels/) · [Self Service APIs](${BASE}/tdd/apis/master/)
- **[lsb CLI User Guide](${BASE}/guides/cli/)** — Install \`lsb\` via \`uv tool install\`, sign in with Google Cloud ADC, and inspect platform health and roles.
`;

  return {
    raw: md.trim(),
    data: {
      title: 'Crucible',
      description:
        'Governed, multi-tenant Google Cloud & AI learning sandboxes orchestrated from a central Control Tower.',
      template: 'splash' as const,
      hero: {
        title: 'Governed cloud learning sandboxes. Built for scale.',
        tagline:
          'Crucible separates Central IT financial & guardrail governance from self-service shared playgrounds and isolated student app workspaces on Google Cloud.',
        image: {
          html: `<img src="${BASE}/favicon.svg" alt="Red smelting crucible" width="220" height="220" class="crucible-hero-mark" />`,
        },
        actions: [
          {
            text: 'Conceptual Framework',
            link: `${BASE}/brs/master/`,
            icon: 'right-arrow' as const,
            variant: 'primary' as const,
          },
          {
            text: 'Technical Design (TDD)',
            link: `${BASE}/tdd/master/`,
            variant: 'secondary' as const,
          },
          {
            text: 'GitHub',
            link: `https://github.com/shankyram1912/crucible-learning-sandbox`,
            icon: 'external' as const,
            variant: 'minimal' as const,
          },
        ],
      },
    },
  };
}

function repoMarkdownLoader(): Loader {
  return {
    name: 'crucible-repo-markdown-loader',
    load: async ({ config, store, parseData, generateDigest, entryTypes, logger, watcher }) => {
      store.clear();

      const mdEntryType = entryTypes.get('.md');
      if (!mdEntryType?.getRenderFunction) {
        throw new Error('Markdown entryType renderer unavailable in Astro config.');
      }
      const renderMd = await mdEntryType.getRenderFunction(config);
      const docsVirtualRoot = resolve(siteSrcDir, 'content', 'docs');

      // 1. Landing splash page (in-memory, slug 'index')
      const landing = buildLandingPage();
      const landingVirtualPath = resolve(docsVirtualRoot, 'index.md');
      const landingDigest = generateDigest(landing.raw);
      const landingData = await parseData({ id: 'index', data: landing.data, filePath: landingVirtualPath });
      const landingRendered = await renderMd({
        id: 'index',
        data: landing.data,
        body: landing.raw,
        filePath: landingVirtualPath,
        digest: landingDigest,
      });
      store.set({
        id: 'index',
        data: landingData,
        body: landing.raw,
        digest: landingDigest,
        rendered: landingRendered,
      });

      // 2. Load every spec & guide directly from ../specs, ../guides, ../todolist.md (zero disk copy)
      for (const page of PAGES) {
        const absPath = resolve(repoRoot, page.source);
        if (!existsSync(absPath)) {
          logger.warn(`Skipping missing doc source: ${page.source}`);
          continue;
        }
        watcher?.add(absPath);

        const rawFile = readFileSync(absPath, 'utf-8');
        let h1Title = page.title;
        let body = rawFile;

        // Strip leading `# H1` so Starlight doesn't render a duplicate page heading
        const h1Match = body.match(/^#\s+(.+?)\r?\n+/);
        if (h1Match) {
          if (!h1Title) h1Title = h1Match[1].replace(/`/g, '').trim();
          body = body.slice(h1Match[0].length);
        }

        const rewritten = rewriteLinks(body, page.source);
        const frontmatter = {
          title: h1Title ?? page.slug,
          description: page.description,
          editUrl: `${GH_BLOB}${page.source}`,
        };

        // Virtual path under src/content/docs/ enables Starlight's heading-anchor plugin
        const virtualDocsPath = resolve(docsVirtualRoot, `${page.slug}.md`);
        const digest = generateDigest(rewritten);
        const data = await parseData({ id: page.slug, data: frontmatter, filePath: virtualDocsPath });
        const rendered = await renderMd({
          id: page.slug,
          data: frontmatter,
          body: rewritten,
          filePath: virtualDocsPath,
          digest,
        });

        store.set({
          id: page.slug,
          data,
          body: rewritten,
          filePath: page.source,
          digest,
          rendered,
        });
      }
    },
  };
}

export const collections = {
  docs: defineCollection({
    loader: repoMarkdownLoader(),
    schema: docsSchema(),
  }),
};
