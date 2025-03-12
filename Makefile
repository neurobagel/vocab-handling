.PHONY: all generate clean diagnosis

vocab/diagnosis/diagnoses.json:
	python -m src/generate_diagnosis.py

diagnosis: vocab/diagnosis/diagnoses.json