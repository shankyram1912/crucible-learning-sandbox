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
  // Single contiguous CommonMark HTML block (no blank lines or 4-space indents, which CommonMark treats as <pre><code>)
  const md = [
    `<div class="c-pillars not-content">`,
    `<div class="c-pillars-head">`,
    `<div class="c-pillars-flow" aria-label="Documentation Reading Order">`,
    `<span>01 Conceptual Architecture</span><i aria-hidden="true">&rarr;</i><span>02 Specifications</span><i aria-hidden="true">&rarr;</i><span>03 Deployment &amp; User Guides</span>`,
    `</div>`,
    `<h2>Documentation</h2>`,
    `<p>Follow the platform from the conceptual framework and persona journeys, to technical specifications, to Day-0 bootstrap and CLI guides.</p>`,
    `</div>`,
    `<div class="c-card-grid">`,
    `<div class="c-pillar-card">`,
    `<div class="c-pillar-top">`,
    `<div class="c-card-eyebrow">01 &middot; Conceptual Architecture</div>`,
    `<h3><a href="${BASE}/brs/master/">Conceptual Framework &amp; Journeys</a></h3>`,
    `<p>The business problem, layered conceptual model, personas, playground organization, core business rules, and persona journeys.</p>`,
    `</div>`,
    `<ul class="c-pillar-links">`,
    `<li><a href="${BASE}/brs/master/"><span>Business Requirements &amp; Conceptual Framework</span><i>&rarr;</i></a></li>`,
    `<li><a href="${BASE}/brs/it-admin-cuj/"><span>IT Admin Journeys</span><i>&rarr;</i></a></li>`,
    `<li><a href="${BASE}/brs/bu-admin-cuj/"><span>BU Admin &amp; Playground Admin Journeys</span><i>&rarr;</i></a></li>`,
    `<li><a href="${BASE}/brs/student-cuj/"><span>Student &amp; Designated User Journeys</span><i>&rarr;</i></a></li>`,
    `</ul>`,
    `</div>`,
    `<div class="c-pillar-card">`,
    `<div class="c-pillar-top">`,
    `<div class="c-card-eyebrow">02 &middot; Specifications</div>`,
    `<h3><a href="${BASE}/tdd/master/">Technical Design (TDD)</a></h3>`,
    `<p>Control Tower Terraform and IAM principles, tag and label binding, playground pipeline and GCP services, Firestore data design, and Self Service APIs.</p>`,
    `</div>`,
    `<ul class="c-pillar-links">`,
    `<li><a href="${BASE}/tdd/master/"><span>Control Tower TDD: Terraform &amp; IAM Principles</span><i>&rarr;</i></a></li>`,
    `<li><a href="${BASE}/tdd/tags-labels/"><span>Tag and Label Binding</span><i>&rarr;</i></a></li>`,
    `<li><a href="${BASE}/tdd/playground-pipeline/"><span>Playground Pipeline &amp; GCP Services</span><i>&rarr;</i></a></li>`,
    `<li><a href="${BASE}/tdd/data/"><span>Firestore Data Design &amp; Config DB</span><i>&rarr;</i></a></li>`,
    `<li><a href="${BASE}/tdd/apis/master/"><span>Self Service APIs &amp; CUJ Operation Map</span><i>&rarr;</i></a></li>`,
    `</ul>`,
    `</div>`,
    `<div class="c-pillar-card">`,
    `<div class="c-pillar-top">`,
    `<div class="c-card-eyebrow">03 &middot; Deployment &amp; User Guides</div>`,
    `<h3><a href="${BASE}/deploy/control-tower/">Deploy &amp; Operate</a></h3>`,
    `<p>Bootstrap the Control Tower in Google Cloud Shell, run the local API server, and use the <code>lsb</code> command-line interface.</p>`,
    `</div>`,
    `<ul class="c-pillar-links">`,
    `<li><a href="${BASE}/deploy/control-tower/"><span>Control Tower Day-0 Bootstrap Runbook</span><i>&rarr;</i></a></li>`,
    `<li><a href="${BASE}/deploy/api/"><span>lsb-api Local Server &amp; Developer Guide</span><i>&rarr;</i></a></li>`,
    `<li><a href="${BASE}/deploy/cli/"><span>lsb-cli Developer Guide</span><i>&rarr;</i></a></li>`,
    `<li><a href="${BASE}/guides/cli/"><span>lsb CLI User Guide</span><i>&rarr;</i></a></li>`,
    `<li><a href="${BASE}/roadmap/todolist/"><span>Build Sequence &amp; Status</span><i>&rarr;</i></a></li>`,
    `<li><a href="${BASE}/roadmap/dedicated-playground-sandboxes/"><span>Roadmap: Dedicated Playground Sandboxes</span><i>&rarr;</i></a></li>`,
    `</ul>`,
    `</div>`,
    `</div>`,
    `</div>`,
  ].join('\n');

  return {
    raw: md.trim(),
    data: {
      title: 'Crucible',
      description:
        'Crucible (Learning Sandbox): a self-service platform run from a central Control Tower on Google Cloud.',
      template: 'splash' as const,
      hero: {
        title: 'Govern once. Self-serve playgrounds and workspaces.',
        tagline:
          'Crucible (Learning Sandbox) runs from a central Control Tower on Google Cloud so IT Admins govern catalogs and Playground Folders once, while BU Admins and Playground Users serve themselves inside those rules.',
        actions: [
          {
            text: 'Conceptual Architecture',
            link: `${BASE}/brs/master/`,
            icon: 'right-arrow' as const,
            variant: 'primary' as const,
          },
          {
            text: 'Specifications',
            link: `${BASE}/tdd/master/`,
            variant: 'secondary' as const,
          },
          {
            text: 'Deployment & Guides',
            link: `${BASE}/deploy/control-tower/`,
            variant: 'secondary' as const,
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

      // 2. Load every spec & guide directly from ../specs, ../src, ../guides, ../todolist.md (zero disk copy)
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
