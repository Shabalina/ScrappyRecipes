# Terraform — environment isolation via workspaces

qa and prod share this one root module (selected via `-var-file`), but each **must** use
its own Terraform workspace so their state never mixes. Without this, applying with
`-var-file=environments/prod.tfvars` against the same state qa used would see qa's
`create_ecr_repository`/`create_github_oidc_provider` resources as no longer wanted (prod
sets both `false`) and plan to **destroy** them.

Workspaces: `qa`, `prod`, plus the built-in `default` (unused — kept empty, never apply
against it).

## Local usage

Always select the workspace matching the `-var-file` you're passing, for every `plan` and
`apply`:

```sh
terraform workspace select qa
terraform plan  -var-file=environments/qa.tfvars  -var-file=environments/qa.secrets.tfvars
terraform apply -var-file=environments/qa.tfvars  -var-file=environments/qa.secrets.tfvars
```

```sh
terraform workspace select prod
terraform plan  -var-file=environments/prod.tfvars  -var-file=environments/prod.secrets.tfvars
terraform apply -var-file=environments/prod.tfvars  -var-file=environments/prod.secrets.tfvars
```

(`*.secrets.tfvars` — copy from `environments/terraform.tfvars.example`, gitignored, never
committed.)

`terraform workspace select <name>` fails if the workspace doesn't exist yet; both `qa` and
`prod` already exist in this repo's state, so `select` (not `new`) is correct going forward.

## CI (GitHub Actions)

Every job that runs `terraform plan`/`apply` must select the workspace matching the
environment it's deploying, immediately after `terraform init` and before any `plan`/
`apply` step — e.g.:

```yaml
- name: Terraform init
  run: terraform init
  working-directory: terraform

- name: Select workspace
  run: terraform workspace select ${{ inputs.environment }}   # "qa" or "prod"
  working-directory: terraform

- name: Terraform plan
  run: terraform plan -var-file=environments/${{ inputs.environment }}.tfvars
  working-directory: terraform
```

Never let a workflow run `plan`/`apply` on whatever workspace happens to be selected by
default — always select explicitly first, keyed off the same environment input that picks
the `-var-file`.

## Why qa owns the shared resources

`create_ecr_repository` / `create_github_oidc_provider` are `true` only in `qa.tfvars`.
qa's workspace state is the source of truth for the shared ECR repository and GitHub OIDC
provider; prod's workspace reads both via data source (live AWS lookup by name, not a
state lookup, so it works regardless of workspace). Apply qa before prod for a from-scratch
setup.
