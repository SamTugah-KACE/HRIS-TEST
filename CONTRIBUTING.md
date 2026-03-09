# Contributing Guidelines

## Branch Workflow (Required)

All collaborators must follow this workflow before starting any implementation work:

1. Create a new feature branch from `main`.
2. Immediately sync latest `main` into the new branch before writing code.
3. Keep all changes in that branch only.
4. Do not commit directly to `main`.

### Required Commands

```bash
git checkout main
git pull origin main
git checkout -b feat/<short-name>
git merge main
```

## Pull Request Expectations

- Open a pull request from your feature branch.
- Ensure your branch includes the latest `main` changes.
- Resolve merge conflicts in your branch before requesting review.
