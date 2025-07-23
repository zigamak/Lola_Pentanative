import os
import json
from .base_handler import BaseHandler

class FAQHandler(BaseHandler):
    """Handles FAQ-related interactions."""
    
    def __init__(self, config, session_manager, data_manager, whatsapp_service):
        super().__init__(config, session_manager, data_manager, whatsapp_service)
        self.faq_data = self.load_faq_data()
    
    def load_faq_data(self):
        """Load FAQ data from JSON file."""
        try:
            faq_file = "data/faq.json"
            if os.path.exists(faq_file):
                with open(faq_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                self.logger.warning(f"FAQ file {faq_file} not found.")
                return {"categories": {}}
        except Exception as e:
            self.logger.error(f"Error loading FAQ data: {e}")
            return {"categories": {}}
    
    def handle_faq_categories_state(self, state, message, session_id):
        """Handle FAQ category selection."""
        if message.startswith("faq_cat_"):
            category_id = message.replace("faq_cat_", "")
            if category_id in self.faq_data["categories"]:
                state["current_state"] = "faq_questions"
                state["selected_faq_category"] = category_id
                return self.show_faq_questions(session_id, category_id)
            else:
                return self.whatsapp_service.create_text_message(
                    session_id,
                    "❌ Category not found. Please select from the list above."
                )
        elif message == "back":
            state["current_state"] = "enquiry_menu"
            buttons = [
                {"type": "reply", "reply": {"id": "faq", "title": "📚 FAQ"}},
                {"type": "reply", "reply": {"id": "ask_question", "title": "❓ Ask Question"}},
                {"type": "reply", "reply": {"id": "back_to_main", "title": "🔙 Back"}}
            ]
            return self.whatsapp_service.create_button_message(
                session_id,
                "How can we help you today?",
                buttons
            )
        else:
            return self.whatsapp_service.create_text_message(
                session_id,
                "Please select a category from the list above or type 'back'."
            )
    
    def show_faq_categories(self, session_id):
        """Show FAQ categories."""
        if not self.faq_data.get("categories"):
            return self.whatsapp_service.create_text_message(
                session_id,
                "❌ FAQ is currently unavailable. Please ask your question directly."
            )
        
        rows = []
        for category_id, category_data in self.faq_data["categories"].items():
            rows.append({
                "id": f"faq_cat_{category_id}",
                "title": category_data["title"]
            })
        
        sections = [{"title": "FAQ Categories", "rows": rows}]
        
        return self.whatsapp_service.create_list_message(
            session_id,
            "📚 *Frequently Asked Questions*\n\nChoose a category to see common questions and answers:",
            "Categories",
            sections
        )
    
    def show_faq_questions(self, session_id, category_id):
        """Show questions in selected FAQ category."""
        category_data = self.faq_data["categories"][category_id]
        
        rows = []
        for question_id, question_data in category_data["questions"].items():
            # Truncate title for WhatsApp limits
            title = question_data["question"]
            if len(title) > 24:
                title = title[:21] + "..."
            
            rows.append({
                "id": f"faq_q_{category_id}_{question_id}",
                "title": title
            })
        
        sections = [{"title": f"{category_data['title']} Questions", "rows": rows}]
        
        return self.whatsapp_service.create_list_message(
            session_id,
            f"📋 *{category_data['title']} Questions*\n\nSelect a question to see the answer:",
            "Questions",
            sections
        )
    
    def handle_faq_questions_state(self, state, message, session_id):
        """Handle FAQ question selection."""
        if message.startswith("faq_q_"):
            parts = message.split("_")
            if len(parts) >= 4:
                category_id = parts[2]
                question_id = parts[3]
                
                if (category_id in self.faq_data["categories"] and 
                    question_id in self.faq_data["categories"][category_id]["questions"]):
                    
                    question_data = self.faq_data["categories"][category_id]["questions"][question_id]
                    
                    buttons = [
                        {"type": "reply", "reply": {"id": "more_questions", "title": "🔍 More Questions"}},
                        {"type": "reply", "reply": {"id": "ask_question", "title": "❓ Ask Question"}},
                        {"type": "reply", "reply": {"id": "back_to_main", "title": "🏠 Main Menu"}}
                    ]
                    
                    return self.whatsapp_service.create_button_message(
                        session_id,
                        f"❓ *{question_data['question']}*\n\n{question_data['answer']}\n\n---\n\nWas this helpful? Need more assistance?",
                        buttons
                    )
        elif message == "more_questions":
            return self.show_faq_categories(session_id)
        elif message == "ask_question":
            state["current_state"] = "enquiry"
            return self.whatsapp_service.create_text_message(
                session_id,
                "❓ What would you like to know? Please type your question and we'll get back to you soon!"
            )
        elif message == "back_to_main":
            return self.handle_back_to_main(state, session_id)
        elif message == "back":
            category_id = state.get("selected_faq_category")
            if category_id:
                return self.show_faq_questions(session_id, category_id)
            else:
                state["current_state"] = "faq_categories"
                return self.show_faq_categories(session_id)
        
        return self.whatsapp_service.create_text_message(
            session_id,
            "Please select a question from the list above or choose an option."
        )