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
      logo: {
        src: './src/assets/crucible-logo.svg',
        alt: 'Crucible icon',
      },
      description:
        'Crucible (Learning Sandbox): a self-service platform run from a central Control Tower on Google Cloud.',
      favicon: '/crucible-favicon.svg',
      social: [
        {
          icon: 'github',
          label: 'GitHub',
          href: `https://github.com/${OWNER_REPO}`,
        },
      ],
      components: {
        Hero: './src/components/Hero.astro',
        PageFrame: './src/components/PageFrame.astro',
        ThemeProvider: './src/components/ThemeProvider.astro',
        ThemeSelect: './src/components/ThemeSelect.astro',
      },
      sidebar: [
        {
          label: '01 — Conceptual Architecture',
          items: [
            { label: 'Conceptual Framework (BRS Master)', slug: 'brs/master' },
            { label: 'IT Admin Journeys', slug: 'brs/it-admin-cuj' },
            { label: 'BU Admin & Playground Admin Journeys', slug: 'brs/bu-admin-cuj' },
            { label: 'Student & Designated User Journeys', slug: 'brs/student-cuj' },
          ],
        },
        {
          label: '02 — Specifications',
          items: [
            { label: 'Control Tower TDD: Terraform & IAM', slug: 'tdd/master' },
            { label: 'Control Tower Day-0 Bootstrap', slug: 'tdd/control-tower' },
            { label: 'Tag and Label Binding', slug: 'tdd/tags-labels' },
            { label: 'Playground Terraform Pipeline', slug: 'tdd/playground-pipeline' },
            { label: 'Playground GCP Services', slug: 'tdd/playground-services' },
            {
              label: 'Firestore Data Design',
              collapsed: false,
              items: [
                { label: 'Data Master (Conceptual)', slug: 'tdd/data' },
                { label: 'Configuration Entities (Config DB)', slug: 'tdd/data/config' },
              ],
            },
            {
              label: 'Self Service APIs',
              collapsed: false,
              items: [
                { label: 'APIs Master', slug: 'tdd/apis/master' },
                { label: 'CUJ to Operation Map', slug: 'tdd/apis/cuj-map' },
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
        },
        {
          label: '03 — Deployment & User Guides',
          items: [
            { label: 'Control Tower Day-0 Bootstrap Runbook', slug: 'deploy/control-tower' },
            { label: 'lsb-api Local Server & Developer Guide', slug: 'deploy/api' },
            { label: 'lsb-cli Developer Guide', slug: 'deploy/cli' },
            { label: 'lsb CLI User Guide', slug: 'guides/cli' },
            { label: 'Build Sequence & Status', slug: 'roadmap/todolist' },
          ],
        },
        {
          label: '04 — Roadmap',
          items: [
            { label: 'Dedicated Playground Sandboxes', slug: 'roadmap/dedicated-playground-sandboxes' },
          ],
        },
      ],
      customCss: ['katex/dist/katex.min.css', './src/styles/docs.css'],
    }),
  ],
});
