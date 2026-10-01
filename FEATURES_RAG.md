# Feature Spec: General-purpose RAG Bot

## Mục tiêu

Phát triển Telegram bot hiện tại thành trợ lý đa dụng có thể trả lời dựa trên tài liệu do người vận hành cung cấp. Khi câu hỏi cần kiến thức ngoài hội thoại, bot phải truy xuất nguồn liên quan, trả lời có căn cứ và nói rõ khi không tìm thấy đủ thông tin.

Đây là đặc tả tính năng. Các mục RAG bên dưới chưa được triển khai trong phiên bản hiện tại.

## Hiện trạng

- [x] Telegram polling, `/start`, `/help`, `/reset`.
- [x] Chọn Gemini trên Vertex AI hoặc LLM tương thích OpenAI chạy trên Modal.
- [x] Lưu lịch sử hội thoại theo chat trong Valkey; có fallback bộ nhớ tiến trình.
- [ ] Nạp, chia nhỏ và lập chỉ mục tài liệu.
- [ ] Tạo embedding và tìm kiếm bằng vector database.
- [ ] Ground câu trả lời theo kết quả truy xuất và trích dẫn nguồn.
- [ ] Đánh giá chất lượng retrieval và câu trả lời RAG.

## Kiến trúc mục tiêu

```mermaid
flowchart LR
    DOC[Markdown, text, PDF] --> INGEST[Ingestion pipeline]
    INGEST --> CHUNK[Parse, normalize, chunk]
    CHUNK --> EMBED[Embedding provider]
    EMBED --> INDEX[(Qdrant collection)]

    USER[Telegram user] --> BOT[Telegram handlers]
    BOT --> QUERY[Query/context preparation]
    QUERY --> EMBED
    EMBED --> RETRIEVE[Hybrid retrieval and reranking]
    INDEX --> RETRIEVE
    RETRIEVE --> PACK[Context assembly with source metadata]
    PACK --> LLM[Gemini or Modal generation]
    LLM --> CHECK[Grounding and citation checks]
    CHECK --> BOT
    HISTORY[(Valkey conversation history)] <--> BOT
```

Các ranh giới module đề xuất:

- `app/ingest.py`: đọc tài liệu, chuẩn hóa, chunk, embed và upsert.
- `app/embeddings.py`: adapter embedding độc lập với model sinh câu trả lời.
- `app/rag.py`: query preparation, retrieval, reranking và dựng context.
- `app/llm.py`: chỉ sinh câu trả lời từ system prompt, lịch sử hội thoại và context đã truy xuất.
- `app/session.py`: lưu hội thoại ngắn hạn; không dùng session làm kho tri thức.
- `evals/`: dataset và đánh giá retrieval/answer.

## Feature theo mức ưu tiên

### P0: RAG MVP

- [ ] **Document ingestion**: hỗ trợ Markdown và TXT trước; mở rộng PDF có trích xuất trang. Một lệnh CLI ingest/re-ingest tài liệu, báo số file thành công/thất bại và không tạo bản ghi trùng khi chạy lại.
- [ ] **Metadata nguồn**: lưu `document_id`, tên tài liệu, đường dẫn hoặc URL, trang (nếu có), tiêu đề, `chunk_id`, phiên bản/hash và thời điểm cập nhật.
- [ ] **Chunking có thể cấu hình**: chia theo cấu trúc heading/đoạn trước, giới hạn kích thước và overlap sau; không cắt rời metadata nguồn khỏi chunk.
- [ ] **Embedding adapter**: cấu hình riêng `EMBEDDING_PROVIDER` và `EMBEDDING_MODEL`. Cùng một model, dimension và preprocessing phải được dùng cho ingestion lẫn query.
- [ ] **Vector store**: dùng Qdrant cho dense vector và metadata payload; tên collection/version được cấu hình, có lệnh kiểm tra trạng thái index.
- [ ] **Semantic retrieval**: truy xuất top-k chunk, loại kết quả dưới ngưỡng relevance và giữ lại nguồn gốc của từng chunk.
- [ ] **Grounded answer**: đưa các đoạn truy xuất vào context có giới hạn token; yêu cầu LLM chỉ dùng tài liệu cho câu hỏi thuộc phạm vi knowledge base.
- [ ] **Abstention**: nếu không có nguồn phù hợp hoặc bằng chứng mâu thuẫn/thiếu, bot nói chưa đủ thông tin thay vì tự điền bằng kiến thức không dẫn nguồn.
- [ ] **Citations trong Telegram**: trả tên tài liệu và trang/heading/link khi có; citation phải trỏ tới chunk thực sự được đưa vào prompt.
- [ ] **Tách lịch sử và tri thức**: Valkey giữ hội thoại; Qdrant giữ tài liệu. Lịch sử có thể giúp hiểu đại từ/câu hỏi nối tiếp nhưng không được xem là nguồn xác thực cho dữ kiện.

### P1: Nâng chất lượng retrieval

- [ ] **Query contextualization**: viết lại câu hỏi nối tiếp bằng một bước riêng, dựa trên lịch sử gần đây; giữ nguyên ý định, con số và thực thể do người dùng nêu.
- [ ] **Hybrid search**: kết hợp dense retrieval với tìm kiếm từ khóa để xử lý tên riêng, mã, cụm từ chính xác; hợp nhất thứ hạng thay vì cộng điểm không cùng thang đo.
- [ ] **Reranking**: rerank tập ứng viên nhỏ trước khi dựng context; bật/tắt và chọn model qua cấu hình.
- [ ] **Context packing**: loại chunk trùng lặp, ưu tiên nguồn có relevance cao, giữ diversity giữa tài liệu và không vượt token budget.
- [ ] **Metadata filters**: lọc theo tập tài liệu, loại tài liệu, ngôn ngữ hoặc quyền truy cập trước khi trả kết quả.
- [ ] **Source lifecycle**: cập nhật/xóa tài liệu phải xóa hoặc thay thế đúng các chunk cũ; hỗ trợ dry-run và báo cáo thay đổi.

### P2: Vận hành và mở rộng

- [ ] **Nguồn bổ sung**: PDF, HTML/URL và thư mục đồng bộ; parser chạy theo loại MIME, giới hạn kích thước và có trạng thái lỗi riêng từng file.
- [ ] **Quản lý knowledge base**: lệnh/admin API để xem nguồn, ingest lại, xóa tài liệu và kiểm tra số chunk.
- [ ] **Observability**: đo ingest duration, retrieval latency, số chunk truy xuất, điểm relevance, LLM latency, token/cost và lỗi theo provider.
- [ ] **Privacy-aware logging**: mặc định không ghi raw prompt, nội dung tài liệu hay thông tin định danh vào log; có chính sách retention rõ ràng.
- [ ] **Phân quyền**: nếu phục vụ nhiều nhóm người dùng, mọi truy vấn phải áp dụng ACL/tenant filter trước khi trả chunk; không dựa vào prompt để cách ly dữ liệu.
- [ ] **Resilience**: retry có giới hạn cho lỗi transient, timeout riêng cho embedding/vector store/LLM và phản hồi lỗi dễ hiểu khi một dependency ngừng hoạt động.

## Nguyên tắc thiết kế RAG

1. **Retrieval trước generation**: không gửi toàn bộ knowledge base vào prompt; chỉ gửi context liên quan đã truy xuất.
2. **Embedding độc lập với generator**: Gemini/Modal có thể đổi mà không làm thay đổi vector index. Đổi embedding model cần re-index có kiểm soát.
3. **Nguồn luôn đi cùng chunk**: mỗi kết quả phải giữ metadata đủ để hiển thị citation và truy vết về tài liệu gốc.
4. **Không coi similarity là sự thật**: điểm tương đồng chỉ giúp xếp hạng; câu trả lời vẫn cần bằng chứng đủ và kiểm tra citation.
5. **Hội thoại không thay thế knowledge base**: lịch sử chỉ cung cấp ngữ cảnh hội thoại; dữ kiện cần căn cứ phải đến từ nguồn được phép.
6. **Không âm thầm dùng kiến thức ngoài nguồn**: khi RAG được yêu cầu hoặc câu hỏi nằm trong phạm vi tài liệu, thiếu context phải dẫn đến câu trả lời có giới hạn/abstain.

## Tiêu chí nghiệm thu MVP

- Ingest cùng một tập tài liệu hai lần không làm tăng bản ghi trùng; cập nhật hoặc xóa file phản ánh đúng trong Qdrant.
- Một câu hỏi có trong tài liệu trả lời đúng ý và có citation khớp với chunk đã truy xuất.
- Một câu hỏi không có trong tài liệu không tạo ra citation giả và bot nói rõ không đủ căn cứ.
- Câu hỏi nối tiếp như “còn cách thứ hai thì sao?” được contextualize nhưng không làm thay đổi thực thể hoặc ý định ban đầu.
- Có test cho parsing/chunking, metadata, embedding dimensions, retrieval, citation/abstention và provider Gemini/Modal.
- Evaluation report tách riêng chất lượng retrieval và chất lượng câu trả lời; ít nhất theo dõi Recall@k/MRR cho retrieval và citation correctness/groundedness cho answer.
- Lỗi Qdrant hoặc embedding được ghi nhận và trả thông báo phù hợp; bot không giả vờ đã tra cứu tài liệu.

## Ngoài phạm vi MVP

- Fine-tune LLM để thay cho retrieval.
- Agent tự thực thi hành động bên ngoài khi chưa có xác nhận và quyền hạn rõ ràng.
- Coi câu trả lời của model là dữ liệu để tự động đưa ngược vào knowledge base.