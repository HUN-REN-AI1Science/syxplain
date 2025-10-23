# Syxplain

This is a proof of concept system which uses state of the art symbolic regression models to predict a selected variable in a dataset and explain the predicted equations in natural language using large language models. Setting the hiperparameters of the symbolic regression can be tedious, so here we use an LLM withvision capabilities to analyze the dataset and suggest hiperparameters for the symbolic regression model.

## Prerequisites

- Anaconda (Miniconda is suggested)
- GNUPG for credential management
- Gemini API Key (encrypted using gnupg and stored in `credentials/api_key_gemini.gpg`)

The system has been developed and tested on Linux and intented to be used on a Linux environment as a server behind a reverse proxy.

## Installation
After cloning the repository, create a conda environment and install the dependencies. The following lines works only if your current directory is the root of the cloned repository.

```bash
conda env create -f syxplain_environment.yml
conda activate syxplain
```
## Usage

```
python syxplain.py
```
