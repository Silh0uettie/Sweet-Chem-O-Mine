# Conda-Forge Submission

The submission-ready conda-forge v1 recipe is stored in `recipe.yaml`. It
references the MIT-licensed `v0.2.0` GitHub release archive and its SHA-256
checksum.

To submit it:

1. Fork `https://github.com/conda-forge/staged-recipes`.
2. Create a branch from its `main` branch.
3. Copy `recipe.yaml` into:

   ```text
   recipes/sweet-chem-o-mine/recipe.yaml
   ```

4. Commit the recipe and open a pull request to `conda-forge/staged-recipes`.
5. Address the conda-forge CI/reviewer feedback.

After that pull request is merged and the feedstock build completes, users can
install the application with:

```bash
conda create -n scom -c conda-forge python=3.11 sweet-chem-o-mine
conda activate scom
scom
```
