import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { BASE, OWNER_REPO } from './src/pages-map';

export default defineConfig({
  site: 'https://shankyram1912.github.io',
  base: BASE,
  markdown: {
    remarkPlugins: [remarkMath],
    rehypePlugins: [rehypeKatex],
  },
  integrations: [
    starlight({
      title: 'crucible',
      description:
        'Governed, multi-tenant Google Cloud & AI learning sandboxes orchestrated from a central Control Tower.',
      favicon: '/favicon.svg',
      social: [
        {
          icon: 'github',
          label: 'GitHub',
          href: `https://github.com/${OWNER_REPO}`,
        },
      ],
      components: {
        PageFrame: './src/components/PageFrame.astro',
      },
      sidebar: [
        {
          label: 'Start here',
          items: [
            { label: 'Conceptual Framework (BRS)', slug: 'brs/master' },
            { label: 'lsb CLI User Guide', slug: 'guides/cli' },
            { label: 'Build Sequence & To-Do', slug: 'roadmap/todolist' },
          ],
        },
        {
          label: '01 — Business Requirements',
          items: [
            { label: 'BRS Master', slug: 'brs/master' },
            { label: 'IT Admin Journeys (CUJ)', slug: 'brs/it-admin-cuj' },
            { label: 'BU Admin Journeys (CUJ)', slug: 'brs/bu-admin-cuj' },
          ],
        },
        {
          label: '02 — Technical Design',
          items: [
            { label: 'TDD Master (Terraform & IAM)', slug: 'tdd/master' },
            { label: 'Control Tower Day-0 Bootstrap', slug: 'tdd/control-tower' },
            { label: 'Tag & Label Binding Deep Dive', slug: 'tdd/tags-labels' },
            { label: 'Playground Terraform Pipeline', slug: 'tdd/playground-pipeline' },
            { label: 'Playground GCP Services', slug: 'tdd/playground-services' },
            { label: 'Firestore Data Design', slug: 'tdd/data' },
          ],
        },
        {
          label: 'Self Service APIs (TDD)',
          collapsed: false,
          items: [
            { label: 'APIs Master', slug: 'tdd/apis/master' },
            { label: 'Common: Runtime Stack', slug: 'tdd/apis/common-stack' },
            { label: 'Common: Authentication', slug: 'tdd/apis/common-auth' },
            { label: 'Common: Access Control (ACL)', slug: 'tdd/apis/common-acl' },
            { label: 'Common: Models & Errors', slug: 'tdd/apis/common-models' },
            { label: 'Common: Configuration Settings', slug: 'tdd/apis/common-config' },
            { label: 'Common: lsb CLI Conventions', slug: 'tdd/apis/common-cli' },
            { label: 'Common: Jobs (Sync / Async / TF)', slug: 'tdd/apis/common-jobs' },
            { label: 'Domain: Health (01–03)', slug: 'tdd/apis/health' },
            { label: 'Domain: Platform Users (04)', slug: 'tdd/apis/platform-users' },
          ],
        },
      ],
      customCss: ['katex/dist/katex.min.css', './src/styles/docs.css'],
    }),
  ],
});
