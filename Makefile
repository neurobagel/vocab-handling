.PHONY: all generate clean diagnosis

vocab/diagnosis/diagnoses.json:
	python src/generate_vocab.py --mode diagnosis

vocab/assessment/assessments.json:
	python src/generate_vocab.py --mode assessment

diagnosis: vocab/diagnosis/diagnoses.json

assessment: vocab/assessment/assessments.json

all: diagnosis assessment

clean:
	rm -rf vocab/diagnosis
	rm -rf vocab/assessment