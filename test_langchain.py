from dotenv import load_dotenv


def main():
    load_dotenv()
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(model="gpt-4o-mini")
    response = llm.invoke("Explain Django ORM in one sentence.")
    print(response.content)


if __name__ == "__main__":
    main()