repos <- getOption("repos")
if (is.null(repos) || repos["CRAN"] == "@CRAN@") {
  repos <- c(CRAN = "https://cloud.r-project.org")
}

packages <- c(
  "tidyverse",
  "data.table",
  "ggplot2",
  "dplyr",
  "readr",
  "readxl",
  "IRkernel",
  "reticulate"
)

installed <- rownames(installed.packages())
missing <- setdiff(packages, installed)

if (length(missing) > 0) {
  install.packages(missing, repos = repos)
}

IRkernel::installspec(name = "sbs-datascience-r", displayname = "SBS DataScience R")
