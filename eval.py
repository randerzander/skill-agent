#!/usr/bin/env python3
"""
Evaluation script for Agent Skills Framework
Runs test questions from CSV and judges answers
"""
import os
import csv
import json
import yaml
from pathlib import Path
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich.progress import Progress
from agent import AgentSkillsFramework
from utils import load_config

# Load environment
load_dotenv()
console = Console()

def load_test_questions(csv_path, num_questions=5):
    """Load test questions from CSV"""
    questions = []
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if i >= num_questions:
                break
            questions.append({
                'metadata': eval(row['metadata']),  # Parse dict string
                'question': row['problem'],
                'expected_answer': row['answer']
            })
    return questions

def judge_answer(question, expected_answer, agent_answer, judge_model, client):
    """Use judge model to evaluate if agent answer matches expected answer"""
    judge_prompt = f"""You are evaluating whether an AI assistant's answer matches the expected answer to a question.

Question: {question}

Expected Answer: {expected_answer}

Agent's Answer: {agent_answer}

Does the agent's answer correctly provide the same information as the expected answer? 
The answer doesn't need to be word-for-word identical, but it must contain the correct key information.

Respond with a JSON object:
{{
    "correct": true or false,
    "reasoning": "brief explanation of your judgment"
}}"""

    try:
        response = client.chat.completions.create(
            model=judge_model,
            messages=[{"role": "user", "content": judge_prompt}],
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        return result
    except Exception as e:
        console.print(f"[red]Judge error: {e}[/red]")
        return {"correct": False, "reasoning": f"Judge failed: {str(e)}"}

def run_evaluation(num_questions=5, csv_path="data/simple_qa_test_set.csv"):
    """Run evaluation on test questions"""
    console.print("[bold cyan]Agent Skills Framework - Evaluation[/bold cyan]")
    console.print("=" * 80)
    
    # Load config
    config = load_config()
    judge_model = config.get('judge', {}).get('model', 'openai/gpt-4o-mini:free')
    
    # Initialize OpenAI client for judge
    judge_client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY")
    )
    
    # Load test questions
    console.print(f"\n[cyan]Loading {num_questions} test questions...[/cyan]")
    questions = load_test_questions(csv_path, num_questions)
    console.print(f"[green]✓[/green] Loaded {len(questions)} questions")
    
    # Initialize agent
    console.print(f"\n[cyan]Initializing agent...[/cyan]")
    agent = AgentSkillsFramework()
    console.print(f"[green]✓[/green] Agent ready with model: {agent.model}")
    console.print(f"[green]✓[/green] Judge model: {judge_model}")
    
    # Results
    results = []
    
    # Run evaluations
    console.print(f"\n{'=' * 80}")
    console.print("[bold]Running Evaluations[/bold]")
    console.print("=" * 80)
    
    for i, test in enumerate(questions, 1):
        console.print(f"\n[bold cyan]Question {i}/{len(questions)}[/bold cyan]")
        console.print(f"[dim]Topic: {test['metadata']['topic']}[/dim]")
        console.print(f"\n[yellow]Q:[/yellow] {test['question']}")
        console.print(f"[green]Expected:[/green] {test['expected_answer']}")
        
        # Clear agent history and reset metrics for each question
        agent.messages = [agent.messages[0]]  # Keep only system message
        
        # Track metrics
        import time
        start_time = time.time()
        tool_calls = {
            'skill_activations': [],
            'tool_executions': []
        }
        
        # Monkey-patch to track tool calls
        original_run = agent.run
        def tracked_run(user_input, max_iterations=10):
            # We'll track from the conversation log
            return original_run(user_input, max_iterations)
        
        # Get agent's answer
        console.print(f"\n[cyan]→ Asking agent...[/cyan]")
        try:
            agent_answer = agent.run(test['question'], max_iterations=15)
            execution_time = time.time() - start_time
            
            # Parse tool calls from conversation history
            for msg in agent.messages:
                if msg.get('role') == 'assistant' and msg.get('tool_calls'):
                    for tc in msg['tool_calls']:
                        func_name = tc['function']['name']
                        if func_name.startswith('activate_'):
                            skill_name = func_name.replace('activate_', '')
                            tool_calls['skill_activations'].append(skill_name)
                        else:
                            tool_calls['tool_executions'].append(func_name)
            
            console.print(f"\n[blue]Agent:[/blue] {agent_answer[:200]}{'...' if len(agent_answer) > 200 else ''}")
            console.print(f"[dim]⏱ Time: {execution_time:.2f}s | Skills: {', '.join(tool_calls['skill_activations']) or 'none'} | Tools: {', '.join(tool_calls['tool_executions']) or 'none'}[/dim]")
        except Exception as e:
            console.print(f"[red]Error running agent: {e}[/red]")
            agent_answer = f"ERROR: {str(e)}"
            execution_time = time.time() - start_time
        
        # Judge the answer
        console.print(f"\n[cyan]→ Judging answer...[/cyan]")
        judgment = judge_answer(
            test['question'],
            test['expected_answer'],
            agent_answer,
            judge_model,
            judge_client
        )
        
        # Display judgment
        if judgment['correct']:
            console.print(f"[bold green]✓ CORRECT[/bold green]")
        else:
            console.print(f"[bold red]✗ INCORRECT[/bold red]")
        console.print(f"[dim]{judgment['reasoning']}[/dim]")
        
        # Store result with metrics
        results.append({
            'question': test['question'],
            'expected': test['expected_answer'],
            'agent_answer': agent_answer,
            'correct': judgment['correct'],
            'reasoning': judgment['reasoning'],
            'metadata': test['metadata'],
            'execution_time': execution_time,
            'skill_activations': tool_calls['skill_activations'],
            'tool_executions': tool_calls['tool_executions'],
            'num_skill_activations': len(tool_calls['skill_activations']),
            'num_tool_executions': len(tool_calls['tool_executions'])
        })
        
        console.print("-" * 80)
    
    # Summary
    console.print(f"\n{'=' * 80}")
    console.print("[bold]Evaluation Summary[/bold]")
    console.print("=" * 80)
    
    correct_count = sum(1 for r in results if r['correct'])
    accuracy = (correct_count / len(results)) * 100 if results else 0
    
    # Calculate aggregate metrics
    avg_time = sum(r['execution_time'] for r in results) / len(results) if results else 0
    total_skill_activations = sum(r['num_skill_activations'] for r in results)
    total_tool_executions = sum(r['num_tool_executions'] for r in results)
    
    # Create summary table
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Total Questions", str(len(results)))
    table.add_row("Correct", str(correct_count))
    table.add_row("Incorrect", str(len(results) - correct_count))
    table.add_row("Accuracy", f"{accuracy:.1f}%")
    table.add_row("Avg Time", f"{avg_time:.2f}s")
    table.add_row("Total Skill Activations", str(total_skill_activations))
    table.add_row("Total Tool Executions", str(total_tool_executions))
    
    console.print(table)
    
    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = Path("logs") / f"eval_results_{timestamp}.json"
    
    with open(results_file, 'w') as f:
        json.dump({
            'timestamp': timestamp,
            'num_questions': len(results),
            'correct': correct_count,
            'accuracy': accuracy,
            'avg_execution_time': avg_time,
            'total_skill_activations': total_skill_activations,
            'total_tool_executions': total_tool_executions,
            'model': agent.model,
            'judge_model': judge_model,
            'results': results
        }, f, indent=2)
    
    console.print(f"\n[green]✓[/green] Results saved to: {results_file}")
    
    return results, accuracy

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Run agent evaluation")
    parser.add_argument('-n', '--num-questions', type=int, default=5,
                       help='Number of questions to evaluate (default: 5)')
    parser.add_argument('--csv', default='data/simple_qa_test_set.csv',
                       help='Path to CSV file with test questions')
    
    args = parser.parse_args()
    
    run_evaluation(num_questions=args.num_questions, csv_path=args.csv)
