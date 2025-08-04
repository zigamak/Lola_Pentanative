import json
import os
import datetime
import logging
from typing import Dict, List, Any
from .base_handler import BaseHandler

logger = logging.getLogger(__name__)

class FeedbackHandler(BaseHandler):
    """Handles post-order feedback collection and management."""
    
    def __init__(self, config, session_manager, data_manager, whatsapp_service):
        super().__init__(config, session_manager, data_manager, whatsapp_service)
        self.feedback_file = "data/feedback.json"
        self._ensure_feedback_file_exists()
        logger.info("FeedbackHandler initialized.")
    
    def _ensure_feedback_file_exists(self):
        """Ensure feedback JSON file exists."""
        if not os.path.exists(self.feedback_file):
            os.makedirs(os.path.dirname(self.feedback_file), exist_ok=True)
            with open(self.feedback_file, 'w') as f:
                json.dump([], f, indent=2)
            logger.info(f"Created feedback file: {self.feedback_file}")
    
    def initiate_feedback_request(self, state: Dict, session_id: str, order_id: str) -> Dict[str, Any]:
        """
        Initiate feedback collection after successful order completion.
        
        Args:
            state (Dict): Session state
            session_id (str): User's session ID
            order_id (str): Completed order ID
            
        Returns:
            Dict: WhatsApp message response
        """
        try:
            state["current_state"] = "feedback_rating"
            state["current_handler"] = "feedback_handler"
            state["feedback_order_id"] = order_id
            state["feedback_started_at"] = datetime.datetime.now().isoformat()
            self.session_manager.update_session_state(session_id, state)
            
            logger.info(f"Initiated feedback collection for order {order_id}, session {session_id}")
            
            buttons = [
                {"type": "reply", "reply": {"id": "excellent", "title": "🤩 Excellent"}},
                {"type": "reply", "reply": {"id": "good", "title": "😊 Good"}},
                {"type": "reply", "reply": {"id": "bad", "title": "😞 Bad"}}
            ]
            
            message = (
                f"🎉 *Thank you for your order!*\n\n"
                f"📋 Order ID: {order_id}\n\n"
                f"💬 *How was your ordering experience?*\n"
                f"Your feedback helps us improve our service!"
            )
            
            return self.whatsapp_service.create_button_message(session_id, message, buttons)
            
        except Exception as e:
            logger.error(f"Error initiating feedback for order {order_id}: {e}", exc_info=True)
            # Fall back to greeting state
            state["current_state"] = "greeting"
            state["current_handler"] = "greeting_handler"
            self.session_manager.update_session_state(session_id, state)
            # Try to send a simple text message as fallback
            try:
                self.whatsapp_service.create_text_message(
                    session_id,
                    f"Thank you for your order #{order_id}! Your feedback helps us improve. How was your experience? Reply 'excellent', 'good', or 'bad'."
                )
            except:
                pass  # Silent fallback
            return self.handle_back_to_main(state, session_id)
    
    def handle_feedback_rating_state(self, state: Dict, message: str, session_id: str) -> Dict[str, Any]:
        """Handle initial feedback rating selection."""
        logger.debug(f"Handling feedback rating for session {session_id}, message: {message}")
        
        if message in ["excellent", "good", "bad"]:
            return self._handle_any_rating(state, message, session_id)
        elif message == "skip_feedback":
            return self._handle_skip_feedback(state, session_id)
        else:
            # Invalid input, show options again
            return self._show_invalid_rating_message(state, session_id)
    
    def handle_feedback_comment_state(self, state: Dict, message: str, session_id: str) -> Dict[str, Any]:
        """Handle optional feedback comment."""
        logger.debug(f"Handling feedback comment for session {session_id}")
        
        if message.lower() == "skip":
            return self._save_feedback_and_complete(state, session_id, "")
        else:
            return self._save_feedback_and_complete(state, session_id, message)
    
    def _handle_any_rating(self, state: Dict, rating: str, session_id: str) -> Dict[str, Any]:
        """Handles any rating and prompts for a comment."""
        state["feedback_rating"] = rating
        state["current_state"] = "feedback_comment"
        self.session_manager.update_session_state(session_id, state)
        
        return self.whatsapp_service.create_text_message(
            session_id,
            f"Thank you for your feedback! "
        )
    
    def _show_invalid_rating_message(self, state: Dict, session_id: str) -> Dict[str, Any]:
        """Show message for invalid rating input."""
        order_id = state.get("feedback_order_id", "N/A")
        self.whatsapp_service.create_text_message(
            session_id,
            "❌ Please select a valid rating option using the buttons provided."
        )
        return self.initiate_feedback_request(state, session_id, order_id)
    
    def _handle_skip_feedback(self, state: Dict, session_id: str) -> Dict[str, Any]:
        """Handle when user skips feedback."""
        logger.info(f"User {session_id} skipped feedback for order {state.get('feedback_order_id', 'N/A')}")
        
        # Save as skipped feedback
        feedback_data = {
            "phone_number": session_id,
            "user_name": state.get("user_name", "Guest"),
            "order_id": state.get("feedback_order_id", "N/A"),
            "rating": "skipped",
            "comment": "",
            "timestamp": datetime.datetime.now().isoformat(),
            "session_duration": self._calculate_feedback_duration(state)
        }
        
        self._save_feedback_to_file(feedback_data)
        
        # End session with thank you message
        thank_you_msg = "Thank you for your feedback!"
        self.session_manager.clear_full_session(session_id)
        return self.whatsapp_service.create_text_message(session_id, thank_you_msg)
    
    def _save_feedback_and_complete(self, state: Dict, session_id: str, comment: str) -> Dict[str, Any]:
        """Save feedback and end the session."""
        try:
            feedback_data = {
                "phone_number": session_id,
                "user_name": state.get("user_name", "Guest"),
                "order_id": state.get("feedback_order_id", "N/A"),
                "rating": state.get("feedback_rating", "unknown"),
                "comment": comment.strip(),
                "timestamp": datetime.datetime.now().isoformat(),
                "session_duration": self._calculate_feedback_duration(state)
            }
            
            self._save_feedback_to_file(feedback_data)
            
            logger.info(f"Feedback saved for order {feedback_data['order_id']}: {feedback_data['rating']}")
            
            # Thank you message and end session
            thank_you_msg = f"Thank you for your feedback!"
            
            # Clear feedback-related state and end session
            feedback_keys = ["feedback_order_id", "feedback_rating", "feedback_started_at"]
            for key in feedback_keys:
                if key in state:
                    del state[key]
            
            self.session_manager.clear_full_session(session_id)
            
            return self.whatsapp_service.create_text_message(session_id, thank_you_msg)
            
        except Exception as e:
            logger.error(f"Error saving feedback for session {session_id}: {e}", exc_info=True)
            self.session_manager.clear_full_session(session_id)
            return self.whatsapp_service.create_text_message(session_id, "Thank you for your feedback!")
    
    def _save_feedback_to_file(self, feedback_data: Dict) -> None:
        """Save feedback data to JSON file."""
        try:
            # Load existing feedback
            feedback_list = []
            if os.path.exists(self.feedback_file):
                with open(self.feedback_file, 'r') as f:
                    feedback_list = json.load(f)
            
            # Add new feedback
            feedback_list.append(feedback_data)
            
            # Save updated feedback
            with open(self.feedback_file, 'w') as f:
                json.dump(feedback_list, f, indent=2, default=str)
            
            logger.info(f"Feedback saved to {self.feedback_file}")
            
        except Exception as e:
            logger.error(f"Error saving feedback to file: {e}", exc_info=True)
    
    def _calculate_feedback_duration(self, state: Dict) -> float:
        """Calculate how long the feedback session took."""
        try:
            start_time_str = state.get("feedback_started_at")
            if start_time_str:
                start_time = datetime.datetime.fromisoformat(start_time_str)
                duration = (datetime.datetime.now() - start_time).total_seconds()
                return round(duration, 2)
        except Exception as e:
            logger.error(f"Error calculating feedback duration: {e}")
        return 0.0
    
    def _complete_feedback_flow(self, state: Dict, session_id: str, message: str) -> Dict[str, Any]:
        """Complete feedback flow and return to main menu."""
        # Clean up feedback-related state
        feedback_keys = ["feedback_order_id", "feedback_rating", "feedback_started_at"]
        for key in feedback_keys:
            if key in state:
                del state[key]
        
        # Return to main menu
        return self.handle_back_to_main(state, session_id, message)
    
    def get_feedback_analytics(self) -> Dict[str, Any]:
        """Get feedback analytics summary."""
        try:
            if not os.path.exists(self.feedback_file):
                return {"total_feedback": 0, "message": "No feedback data available"}
            
            with open(self.feedback_file, 'r') as f:
                feedback_list = json.load(f)
            
            if not feedback_list:
                return {"total_feedback": 0, "message": "No feedback data available"}
            
            total_feedback = len(feedback_list)
            rating_counts = {}
            total_comments = 0
            recent_feedback = []
            
            for feedback in feedback_list:
                rating = feedback.get("rating", "unknown")
                rating_counts[rating] = rating_counts.get(rating, 0) + 1
                
                if feedback.get("comment", "").strip():
                    total_comments += 1
                
                # Get recent feedback (last 10)
                if len(recent_feedback) < 10:
                    recent_feedback.append({
                        "order_id": feedback.get("order_id", "N/A"),
                        "rating": rating,
                        "comment": feedback.get("comment", "")[:100] + "..." if len(feedback.get("comment", "")) > 100 else feedback.get("comment", ""),
                        "timestamp": feedback.get("timestamp", "N/A")
                    })
            
            # Calculate percentages
            rating_percentages = {
                rating: round((count / total_feedback) * 100, 1)
                for rating, count in rating_counts.items()
            }
            
            return {
                "total_feedback": total_feedback,
                "rating_counts": rating_counts,
                "rating_percentages": rating_percentages,
                "total_comments": total_comments,
                "comment_percentage": round((total_comments / total_feedback) * 100, 1),
                "recent_feedback": recent_feedback,
                "last_updated": datetime.datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting feedback analytics: {e}", exc_info=True)
            return {"error": "Failed to load feedback analytics"}