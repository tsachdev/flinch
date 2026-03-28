from memory.summarizer import summarize_today

print("--- running daily summarizer ---\n")
filepath = summarize_today()

if filepath:
    print("\n--- summary contents ---")
    print(filepath.read_text())