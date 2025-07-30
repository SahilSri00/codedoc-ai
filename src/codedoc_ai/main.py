import typer
app = typer.Typer()
@app.command()
def hello(name: str):
    print(f"Hello {name}, CodeDoc-AI is alive!")
if __name__ == "__main__":
    app()