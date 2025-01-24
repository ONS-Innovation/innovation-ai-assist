# Used to count the number of words in the description column of the SIC knowledge base CSV file
import csv
import json
import re
from collections import Counter, defaultdict

# Input file path
input_file = "ai_assist_builder/data/sic_knowledge_base_utf8.csv"

WORDS_THRESHOLD = 6

# Output file paths
word_tally_file = "ai_assist_builder/data/word_tally.json"
word_brackets_tally_file = "ai_assist_builder/data/word_brackets_tally.json"
word_nonalpha_tally_file = "ai_assist_builder/data/word_nonalpha_tally.json"
word_alpha_only_file = "ai_assist_builder/data/word_alpha_only_tally.json"

WORDS_THRESHOLD = 5


# Function to count words in a string
def count_words(description):
    return len(description.split())


def process_csv(input_file):
    word_count_tally = Counter()
    bracket_word_count_tally = Counter()
    nonalpha_word_count_tally = Counter()
    alpha_threshold_tally = 0

    words_threshold_or_less = 0

    bracket_tally = {"include_brackets": 0, "non_alpha_no_brackets": 0}

    word_details = defaultdict(list)
    bracket_word_details = defaultdict(list)
    nonalpha_word_details = defaultdict(list)

    with open(input_file, newline="", encoding="utf-8") as infile:
        reader = csv.DictReader(infile)

        # Process rows
        for row in reader:
            description = row["description"].strip()
            word_count = count_words(description)

            word_count_tally[word_count] += 1
            word_details[word_count].append(description)

            if word_count <= WORDS_THRESHOLD:
                words_threshold_or_less += 1
                alpha_threshold_tally += 1

            if "(" in description or ")" in description:
                bracket_tally["include_brackets"] += 1
                bracket_word_count_tally[word_count] += 1
                bracket_word_details[word_count].append(description)
                if word_count <= WORDS_THRESHOLD:
                    alpha_threshold_tally -= 1

            elif re.search(r"[^a-zA-Z\s]", description):
                bracket_tally["non_alpha_no_brackets"] += 1
                nonalpha_word_count_tally[word_count] += 1
                nonalpha_word_details[word_count].append(description)
                if word_count <= WORDS_THRESHOLD:
                    alpha_threshold_tally -= 1

    word_tally = [{"words": count, "description_count": occurrences, "word_list": word_details[count]}
                  for count, occurrences in word_count_tally.items()]
    word_brackets_tally = [{"words": count, "description_count": occurrences, "word_list": bracket_word_details[count]}
                           for count, occurrences in bracket_word_count_tally.items()]
    word_nonalpha_tally = [{"words": count, "description_count": occurrences, "word_list": nonalpha_word_details[count]}
                           for count, occurrences in nonalpha_word_count_tally.items()]

    # Process rows for filtered words
    alpha_only_word_details = defaultdict(list)
    for count, descriptions in word_details.items():
        for description in descriptions:
            if not re.search(r"[\(\)]", description) and not re.search(r"[^a-zA-Z\s]", description):
                alpha_only_word_details[count].append(description)

    # Prepare data structure for alpha-only word tally
    word_alpha_only_tally = [
        {"words": count, "description_count": len(descriptions), "word_list": descriptions}
        for count, descriptions in alpha_only_word_details.items()
    ]

    return word_tally, word_brackets_tally, word_nonalpha_tally, word_alpha_only_tally, bracket_tally, words_threshold_or_less, alpha_threshold_tally


# Run the function
word_tally, word_brackets_tally, word_nonalpha_tally, word_alpha_only_tally, bracket_tally, threshold_words, alpha_threshold_words = process_csv(input_file)

# Save filtered alpha-only words to a JSON file
with open(word_alpha_only_file, "w", encoding="utf-8") as f:
    json.dump(word_alpha_only_tally, f, ensure_ascii=False, indent=4)

# Save results to JSON files
with open(word_tally_file, "w", encoding="utf-8") as f:
    json.dump(word_tally, f, ensure_ascii=False, indent=4)

with open(word_brackets_tally_file, "w", encoding="utf-8") as f:
    json.dump(word_brackets_tally, f, ensure_ascii=False, indent=4)

with open(word_nonalpha_tally_file, "w", encoding="utf-8") as f:
    json.dump(word_nonalpha_tally, f, ensure_ascii=False, indent=4)

# Print the bracket and non-alphabet character tallies
print(f"Descriptions with brackets: {bracket_tally['include_brackets']}")
print(f"Descriptions with non-alphabet characters but no brackets: {bracket_tally['non_alpha_no_brackets']}")
print(f"Descriptions with {WORDS_THRESHOLD} words or less: {threshold_words}")
print(f"Descriptions with {WORDS_THRESHOLD} words or less excluding brackets and non-alphabet characters: {alpha_threshold_words}")
