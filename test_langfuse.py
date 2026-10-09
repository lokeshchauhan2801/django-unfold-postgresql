from dotenv import load_dotenv


def main():
    load_dotenv()

    from langchain_openai import ChatOpenAI
    from langfuse.langchain import CallbackHandler

    llm = ChatOpenAI(model="gpt-4o-mini")
    langfuse_handler = CallbackHandler()
    response = llm.invoke(
        "Explain langchain and langfuse in one sentence.",
        config={"callbacks": [langfuse_handler]},
    )
    print(response.content)


if __name__ == "__main__":
    main()