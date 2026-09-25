"""Clearly-identified demo/seed graph data for the Public AI Research project.

These entities and relationships are illustrative sample data to demonstrate the
knowledge graph. They are NOT presented as verified research evidence. Every
seeded node and relationship is flagged with a demo marker/evidence string so
the UI (and any downstream consumer) can distinguish it from real sourced data.

The seed data models a realistic AI research taxonomy:

    Artificial Intelligence
        -> Large Language Models
            -> OpenAI (develops) -> GPT
"""

PUBLIC_AI_SLUG = "public-ai-research-source-validation-2026-08-28"

SEED_ENTITIES = [
    {"name": "Artificial Intelligence", "type": "Topic",
     "description": "The field of study concerned with machines performing tasks that normally require human intelligence. (demo seed data)"},
    {"name": "Machine Learning", "type": "Topic",
     "description": "A subset of artificial intelligence focused on systems that learn from data. (demo seed data)"},
    {"name": "Large Language Models", "type": "Technology",
     "description": "Neural network models trained on vast text corpora to generate and understand language. (demo seed data)"},
    {"name": "Natural Language Processing", "type": "Technology",
     "description": "The branch of AI that enables machines to understand and generate human language. (demo seed data)"},
    {"name": "Neural Networks", "type": "Technology",
     "description": "Computational systems inspired by biological neurons used in modern machine learning. (demo seed data)"},
    {"name": "Transformer", "type": "Technology",
     "description": "A neural network architecture, the foundation of modern large language models. (demo seed data)"},
    {"name": "OpenAI", "type": "Organization",
     "description": "An AI research and deployment organization. (demo seed data)"},
    {"name": "DeepMind", "type": "Organization",
     "description": "An AI research laboratory. (demo seed data)"},
    {"name": "GPT", "type": "Technology",
     "description": "Generative Pre-trained Transformer, a family of language models developed by OpenAI. (demo seed data)"},
    {"name": "ChatGPT", "type": "Technology",
     "description": "A conversational AI assistant built on GPT models by OpenAI. (demo seed data)"},
]

SEED_RELATIONSHIPS = [
    {"fromName": "OpenAI", "toName": "GPT", "relationship": "DEVELOPS",
     "evidence": "(demo seed relationship) OpenAI is the lab that develops the GPT model family."},
    {"fromName": "OpenAI", "toName": "ChatGPT", "relationship": "DEVELOPS",
     "evidence": "(demo seed relationship) OpenAI develops the ChatGPT assistant."},
    {"fromName": "OpenAI", "toName": "Large Language Models", "relationship": "DEVELOPS",
     "evidence": "(demo seed relationship) OpenAI builds large language models."},
    {"fromName": "DeepMind", "toName": "Neural Networks", "relationship": "DEVELOPS",
     "evidence": "(demo seed relationship) DeepMind researches and develops neural network systems."},
    {"fromName": "Large Language Models", "toName": "Artificial Intelligence", "relationship": "BELONGS_TO",
     "evidence": "(demo seed relationship) Large language models are a sub-area of artificial intelligence."},
    {"fromName": "Machine Learning", "toName": "Artificial Intelligence", "relationship": "BELONGS_TO",
     "evidence": "(demo seed relationship) Machine learning is a subfield of artificial intelligence."},
    {"fromName": "Neural Networks", "toName": "Machine Learning", "relationship": "BELONGS_TO",
     "evidence": "(demo seed relationship) Neural networks are a core technique within machine learning."},
    {"fromName": "GPT", "toName": "Large Language Models", "relationship": "BELONGS_TO",
     "evidence": "(demo seed relationship) GPT is a type of large language model."},
    {"fromName": "ChatGPT", "toName": "Large Language Models", "relationship": "BELONGS_TO",
     "evidence": "(demo seed relationship) ChatGPT is built on a large language model."},
    {"fromName": "Large Language Models", "toName": "Natural Language Processing", "relationship": "RELATED_TO",
     "evidence": "(demo seed relationship) Large language models are a core tool in natural language processing."},
    {"fromName": "Transformer", "toName": "Neural Networks", "relationship": "BELONGS_TO",
     "evidence": "(demo seed relationship) Transformers are a neural network architecture."},
    {"fromName": "OpenAI", "toName": "DeepMind", "relationship": "RELATED_TO",
     "evidence": "(demo seed relationship) OpenAI and DeepMind are both leading AI research organizations."},
]
